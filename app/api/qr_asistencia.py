"""
Rutas públicas para asistencia por QR: formulario (GET) y registro (POST).
URL del QR: {APP_BASE_URL}/qr/asistencia?token=XYZ
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel, Field

from app.config import supabase_admin
from app.services.qr_token_service import validate_qr_token

router = APIRouter(prefix="/qr", tags=["qr"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_sb = supabase_admin
if not _sb:
    from app.config import supabase
    _sb = supabase


def _get_event_or_fail(event_id: int, now_utc: datetime):
    """Obtiene evento; lanza HTTPException si no existe o no está vigente."""
    r = _sb.table("events").select("*").eq("id", event_id).execute()
    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado")
    event = r.data[0]
    if not event.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El evento no está activo")
    if event.get("status") != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El evento no está disponible para registrar asistencia")
    start = event.get("start_date")
    end = event.get("end_date")
    if start and end:
        try:
            if isinstance(start, str):
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            else:
                start_dt = start
            if isinstance(end, str):
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            else:
                end_dt = end
            if now_utc < start_dt:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El evento aún no ha comenzado")
            if now_utc > end_dt:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El evento ya finalizó")
        except HTTPException:
            raise
        except Exception:
            pass
    return event


class QrAsistenciaSubmit(BaseModel):
    token: str = Field(min_length=10, max_length=500)
    names: str = Field(min_length=2, max_length=300)
    email: str | None = Field(default=None, max_length=200)
    cedula: str | None = Field(default=None, max_length=50)


@router.get("/asistencia", response_class=HTMLResponse)
async def qr_asistencia_form(request: Request, token: str = ""):
    """
    Muestra el formulario de asistencia. Requiere ?token= en la URL.
    Si el token es inválido o expirado, muestra mensaje de error en HTML.
    """
    if not token:
        return templates.TemplateResponse(
            "qr_asistencia_form.html",
            {"request": request, "error": "Falta el código del QR. Escanea el código QR del evento.", "event_title": None, "token": ""},
        )
    parsed = validate_qr_token(token)
    if not parsed:
        return templates.TemplateResponse(
            "qr_asistencia_form.html",
            {"request": request, "error": "Código QR inválido o expirado.", "event_title": None, "token": ""},
        )
    event_id, _ = parsed
    now_utc = datetime.now(timezone.utc)
    try:
        event = _get_event_or_fail(event_id, now_utc)
    except HTTPException as e:
        return templates.TemplateResponse(
            "qr_asistencia_form.html",
            {"request": request, "error": e.detail, "event_title": None, "token": ""},
        )
    return templates.TemplateResponse(
        "qr_asistencia_form.html",
        {"request": request, "error": None, "event_title": event.get("title"), "token": token},
    )


@router.post("/asistencia")
async def qr_asistencia_submit(payload: QrAsistenciaSubmit):
    """
    Registra la asistencia: valida token, evento vigente, evita duplicados (por email o cédula).
    """
    parsed = validate_qr_token(payload.token)
    if not parsed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código QR inválido o expirado")
    event_id, _ = parsed
    now_utc = datetime.now(timezone.utc)
    event = _get_event_or_fail(event_id, now_utc)
    names = (payload.names or "").strip()
    if not names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombres son obligatorios")
    email = (payload.email or "").strip() or None
    cedula = (payload.cedula or "").strip() or None
    if not email and not cedula:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indica correo o cédula")

    # Evitar duplicados: mismo evento + mismo email o misma cédula
    if email:
        ex = _sb.table("event_checkins").select("id").eq("event_id", event_id).eq("email", email.strip()).execute()
        if ex.data and len(ex.data) > 0:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"success": False, "message": "Ya registrado", "duplicate": True},
            )
    if cedula:
        ex = _sb.table("event_checkins").select("id").eq("event_id", event_id).eq("cedula", cedula.strip()).execute()
        if ex.data and len(ex.data) > 0:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"success": False, "message": "Ya registrado", "duplicate": True},
            )
    try:
        ins = _sb.table("event_checkins").insert({
            "event_id": event_id,
            "names": names,
            "email": email,
            "cedula": cedula,
        }).execute()
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "already exists" in err:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"success": False, "message": "Ya registrado", "duplicate": True},
            )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al registrar la asistencia")

    if not ins.data or len(ins.data) == 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al registrar la asistencia")
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"success": True, "message": "Asistencia registrada ✅"},
    )
