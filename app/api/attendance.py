"""
API de gestión de asistencia a eventos usando Supabase.
Sistema unificado: solo usuarios autenticados e inscritos pueden registrar asistencia.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
from pydantic import BaseModel, Field
from pathlib import Path

from app.config import supabase, supabase_admin, APP_BASE_URL, PUCE_ALLOWED_DOMAINS
from app.schemas.attendance import AttendanceRead
from app.auth import get_current_user, get_current_user_optional, require_admin
from app.services.qr_service import generate_qr_png_bytes
from app.services.qr_token_service import generate_qr_token, validate_qr_token
from app.services.email import send_event_email
from app.services.calendar import build_ics
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional
from fastapi import Depends


router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _sb():
    """Cliente con permisos para leer/escribir (evita RLS desde backend)."""
    return supabase_admin if supabase_admin else supabase


def _normalize_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    return []


def _to_utc(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = value
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


try:
    LOCAL_TZ = ZoneInfo("America/Guayaquil")
except ZoneInfoNotFoundError:
    LOCAL_TZ = timezone(timedelta(hours=-5))


def _to_local_event(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = value
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


MONTHS_ES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def _format_date_es_local(dt: datetime) -> str:
    return f"{dt.day} de {MONTHS_ES[dt.month - 1]} de {dt.year}"


def _format_time_es_local(dt: datetime) -> str:
    return dt.strftime("%H:%M")


class QRScanRequest(BaseModel):
    """Request para escanear QR y registrar asistencia."""
    token: str = Field(min_length=10, max_length=500, description="Token QR del evento")


@router.post(
    "/enroll/{event_id}",
    response_model=AttendanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Inscribirse a un evento aprobado",
)
async def enroll_to_event(
    event_id: int,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Inscribe al usuario actual a un evento aprobado.
    Requiere autenticación. El evento debe estar aprobado y activo.
    Al inscribirse, se crea un registro en attendances con attended=False.
    """
    try:
        sb = _sb()
        user_id = str(current_user["id"])

        event_response = sb.table("events").select("*").eq("id", event_id).execute()
        if not event_response.data or len(event_response.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado")
        
        event = event_response.data[0]

        if event.get("status") != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Solo puedes inscribirte a eventos aprobados"
            )
        
        if not event.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="El evento no está activo"
            )

        user_role = (current_user.get("role") or current_user.get("user_metadata", {}).get("role") or "").lower()
        user_email = (current_user.get("email") or "").lower()
        creator_id = event.get("creator_id")
        creator_email = (event.get("creator_email") or "").lower()
        if user_role == "teacher":
            if (creator_id and str(creator_id) == str(current_user["id"])) or (creator_email and creator_email == user_email):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No puedes inscribirte a un evento que tú mismo organizaste."
                )

        access_type = (event.get("access_type") or event.get("audience") or "publico").lower()
        if access_type in ["puce_only", "interno"]:
            if not user_email.endswith("@pucesm.edu.ec"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Este evento es exclusivo para PUCE. Inicia sesión con tu correo institucional (@pucesm.edu.ec) para inscribirte."
                )

        if event.get("capacity"):
            count_response = sb.table("attendances").select("id", count="exact").eq("event_id", event_id).execute()
            current_count = count_response.count if hasattr(count_response, "count") else len(count_response.data or [])
            if current_count >= event["capacity"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="El evento ha alcanzado su capacidad máxima"
                )

        existing_response = sb.table("attendances").select("*").eq("user_id", user_id).eq("event_id", event_id).execute()
        if existing_response.data and len(existing_response.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail="Ya estás inscrito en este evento"
            )

        attendance_data = {
            "user_id": user_id, 
            "event_id": event_id, 
            "attended": False
        }
        
        response = sb.table("attendances").insert(attendance_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Error al inscribirse al evento"
            )

        row = response.data[0]

        start_dt = _to_local_event(event.get("start_date"))
        end_dt = _to_local_event(event.get("end_date"))
        if start_dt and end_dt:
            description_parts = []
            if event.get("description"):
                description_parts.append(str(event.get("description")))
            if event.get("location"):
                description_parts.append(f"Ubicación: {event.get('location')}")
            description = "\n".join(description_parts)
            ics = build_ics(
                event_id=event.get("id"),
                title=event.get("title") or "Evento académico",
                start_dt=start_dt,
                end_dt=end_dt,
                description=description,
            )

            formatted_date = _format_date_es_local(start_dt)
            formatted_time = _format_time_es_local(start_dt)
            event_title = event.get("title") or "Evento académico"
            event_location = event.get("location") or "Por confirmar"
            event_type = event.get("event_type") or "Evento académico"
            time_line = f"{formatted_date} {('a las ' + formatted_time) if formatted_time else ''}".strip()
            html = f"""
            <div style="font-family:Arial,Helvetica,sans-serif;background-color:#f4f6fb;padding:24px;">
                <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e3e7f0;">
                    <div style="background:#0c3c78;color:#ffffff;padding:20px 24px;">
                        <div style="font-size:14px;letter-spacing:0.5px;text-transform:uppercase;">PUCE Manabí · Eventos Académicos</div>
                        <h1 style="margin:6px 0 0;font-size:22px;">Inscripción confirmada</h1>
                    </div>
                    <div style="padding:22px 24px;color:#1f2a44;">
                        <p style="margin:0 0 12px;">Hola, tu inscripción se registró correctamente.</p>
                        <div style="padding:14px 16px;border:1px solid #e6ebf5;border-radius:10px;background:#f9fafc;">
                            <div style="font-size:16px;font-weight:600;margin-bottom:6px;">{event_title}</div>
                            <div style="font-size:13px;color:#2a3d66;">{event_type}</div>
                            <div style="margin-top:10px;font-size:13px;">
                                <div><strong>Fecha:</strong> {time_line}</div>
                                <div><strong>Ubicación:</strong> {event_location}</div>
                            </div>
                        </div>
                        <p style="margin:16px 0 0;font-size:13px;color:#2a3d66;">
                            Adjuntamos el archivo del calendario para que puedas agregar el evento a tu agenda.
                        </p>
                    </div>
                    <div style="padding:14px 24px;background:#f2f5fb;color:#2a3d66;font-size:12px;">
                        Si tienes dudas, responde a este correo.
                    </div>
                </div>
            </div>
            """
            background.add_task(
                send_event_email,
                current_user.get("email"),
                f"Inscripción confirmada: {event.get('title') or 'Evento académico'}",
                html,
                ics,
            )

        return {
            "id": row["id"],
            "event_id": event_id,
            "user_id": str(user_id),  # Asegurar que sea string
            "status": "enrolled",
            "attended_at": None,
            "created_at": row.get("created_at") or row.get("timestamp"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error al inscribirse al evento: {str(e)}"
        )


@router.get(
    "/check-enrollment/{event_id}",
    summary="Verificar si el usuario está inscrito en un evento",
)
async def check_enrollment(
    event_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Verifica si el usuario actual está inscrito en un evento."""
    try:
        sb = _sb()
        user_id = str(current_user["id"])
        response = sb.table("attendances").select("*").eq("user_id", user_id).eq("event_id", event_id).execute()
        
        if response.data and len(response.data) > 0:
            att = response.data[0]
            return {
                "enrolled": True, 
                "attendance_id": att["id"], 
                "attended": att.get("attended", False),
                "attended_at": att.get("attended_at")
            }
        
        return {
            "enrolled": False, 
            "attendance_id": None, 
            "attended": False,
            "attended_at": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error al verificar inscripción: {str(e)}"
        )


@router.get(
    "/event/{event_id}/qr-image",
    summary="Generar imagen QR del evento (admin/profesor)",
)
async def get_event_qr_image(
    request: Request,
    event_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Genera una imagen PNG del código QR para el evento.
    Solo el creador del evento o un admin puede generar el QR.
    El QR contiene un token que identifica el evento y expira después de la fecha de fin.
    """
    sb = _sb()
    
    event_response = sb.table("events").select("*").eq("id", event_id).execute()
    if not event_response.data or len(event_response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Evento no encontrado"
        )
    
    event = event_response.data[0]
    user_role = (current_user.get("user_metadata") or {}).get("role") or current_user.get("role", "student")
    
    if str(event.get("creator_id")) != str(current_user["id"]) and user_role not in ["admin", "teacher"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Solo el creador del evento o un administrador pueden generar el QR"
        )
    
    end_date = event.get("end_date")
    expiry_ts = None
    
    if end_date:
        try:
            if isinstance(end_date, str):
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            else:
                end_dt = end_date
            
            expiry_ts = int((end_dt + timedelta(days=1)).timestamp())
        except Exception:
            pass
    
    token = generate_qr_token(event_id, expiry_ts=expiry_ts)
    base = (APP_BASE_URL or "").strip().rstrip("/")
    
    if not base or "127.0.0.1" in base or "localhost" in base.lower():
        base = str(request.base_url).rstrip("/")
    
    url = f"{base}/attendance/scan-qr?token={token}"
    png_bytes = generate_qr_png_bytes(url)
    
    return Response(content=png_bytes, media_type="image/png")


@router.get(
    "/scan-qr",
    response_class=HTMLResponse,
    summary="Página para escanear QR y registrar asistencia",
)
async def scan_qr_page(
    request: Request,
    token: str = "",
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Página HTML para escanear QR y registrar asistencia.
    Pública: no requiere autenticación para ver la página.
    Si el usuario está autenticado e inscrito, puede registrar asistencia.
    """
    if not token:
        return templates.TemplateResponse(
            "scan_qr.html",
            {
                "request": request,
                "error": "Falta el código del QR. Escanea el código QR del evento.",
                "event_title": None,
                "success": False,
                "is_authenticated": current_user is not None
            },
        )
    
    parsed = validate_qr_token(token)
    if not parsed:
        return templates.TemplateResponse(
            "scan_qr.html",
            {
                "request": request,
                "error": "Código QR inválido o expirado.",
                "event_title": None,
                "success": False,
                "is_authenticated": current_user is not None
            },
        )
    
    event_id, _ = parsed
    sb = _sb()
    
    event_response = sb.table("events").select("*").eq("id", event_id).execute()
    if not event_response.data or len(event_response.data) == 0:
        return templates.TemplateResponse(
            "scan_qr.html",
            {
                "request": request,
                "error": "Evento no encontrado.",
                "event_title": None,
                "success": False,
                "is_authenticated": current_user is not None
            },
        )
    
    event = event_response.data[0]
    
    if not current_user:
        return templates.TemplateResponse(
            "scan_qr.html",
            {
                "request": request,
                "error": None,
                "event_title": event.get("title"),
                "token": token,
                "success": False,
                "is_authenticated": False,
                "needs_login": True
            },
        )
    
    user_id = str(current_user["id"])
    attendance_response = sb.table("attendances").select("*").eq("user_id", user_id).eq("event_id", event_id).execute()
    
    if not attendance_response.data or len(attendance_response.data) == 0:
        return templates.TemplateResponse(
            "scan_qr.html",
            {
                "request": request,
                "error": "Debes estar inscrito en el evento para registrar asistencia. Ve a la página principal e inscríbete primero.",
                "event_title": event.get("title"),
                "token": token,
                "success": False,
                "is_authenticated": True,
                "needs_enrollment": True
            },
        )
    
    attendance = attendance_response.data[0]

    if event.get("status") != "approved" or not event.get("is_active", False):
        return templates.TemplateResponse(
            "scan_qr.html",
            {
                "request": request,
                "error": "El evento no está disponible para registrar asistencia.",
                "event_title": event.get("title"),
                "success": False,
                "is_authenticated": True
            },
        )
    
    if attendance.get("attended", False):
        attended_at = attendance.get("attended_at")
        attended_date = ""
        if attended_at:
            try:
                if isinstance(attended_at, str):
                    dt = datetime.fromisoformat(attended_at.replace("Z", "+00:00"))
                else:
                    dt = attended_at
                attended_date = dt.strftime("%d/%m/%Y a las %H:%M")
            except Exception:
                attended_date = ""
        
        message = f"Ya registraste tu asistencia a este evento."
        if attended_date:
            message += f" Registrada el {attended_date}."
        
        return templates.TemplateResponse(
            "scan_qr.html",
            {
                "request": request,
                "error": None,
                "event_title": event.get("title"),
                "success": True,
                "message": message,
                "already_registered": True,
                "is_authenticated": True,
                "attended_at": attended_date
            },
        )
    
    # Usuario autenticado e inscrito pero aún no ha registrado asistencia
    # Intentar registrar automáticamente
    try:
        now_utc = datetime.now(timezone.utc)
        start_dt = _to_utc(event.get("start_date"))
        end_dt = _to_utc(event.get("end_date"))

        if start_dt:
            allowed_from = start_dt - timedelta(minutes=5)
            if now_utc < allowed_from:
                return templates.TemplateResponse(
                    "scan_qr.html",
                    {
                        "request": request,
                        "error": "La asistencia estará disponible 5 minutos antes del inicio del evento.",
                        "event_title": event.get("title"),
                        "success": False,
                        "is_authenticated": True
                    },
                )

        if end_dt:
            allowed_until = end_dt + timedelta(minutes=7)
            if now_utc > allowed_until:
                return templates.TemplateResponse(
                    "scan_qr.html",
                    {
                        "request": request,
                        "error": "El tiempo para registrar asistencia ya ha finalizado.",
                        "event_title": event.get("title"),
                        "success": False,
                        "is_authenticated": True
                    },
                )

        update_data = {
            "attended": True,
            "attended_at": now_utc.isoformat()
        }
        
        response = sb.table("attendances").update(update_data).eq("id", attendance["id"]).execute()
        
        if response.data and len(response.data) > 0:
            # Asistencia registrada exitosamente
            attended_at = response.data[0].get("attended_at")
            attended_date = ""
            if attended_at:
                try:
                    if isinstance(attended_at, str):
                        dt = datetime.fromisoformat(attended_at.replace("Z", "+00:00"))
                    else:
                        dt = attended_at
                    attended_date = dt.strftime("%d/%m/%Y a las %H:%M")
                except Exception:
                    attended_date = ""
            
            message = "¡Asistencia registrada exitosamente!"
            if attended_date:
                message += f" Registrada el {attended_date}."
            
            return templates.TemplateResponse(
                "scan_qr.html",
                {
                    "request": request,
                    "error": None,
                    "event_title": event.get("title"),
                    "success": True,
                    "message": message,
                    "already_registered": False,
                    "is_authenticated": True,
                    "attended_at": attended_date,
                    "auto_registered": True
                },
            )
    except Exception as e:
        # Si falla el registro automático, mostrar el botón manual
        pass
    
    return templates.TemplateResponse(
        "scan_qr.html",
        {
            "request": request,
            "error": None,
            "event_title": event.get("title"),
            "token": token,
            "success": False,
            "is_authenticated": True
        },
    )


@router.post(
    "/scan-qr",
    response_model=AttendanceRead,
    status_code=status.HTTP_200_OK,
    summary="Escanear QR y registrar asistencia",
)
async def scan_qr_and_register(
    payload: QRScanRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Escanea un código QR de evento y registra la asistencia.
    
    Requisitos:
    1. Usuario debe estar autenticado
    2. El token QR debe ser válido y no expirado
    3. El evento debe estar activo y aprobado
    4. El usuario debe estar inscrito en el evento
    5. No debe haber registrado asistencia previamente
    
    Si cumple todos los requisitos, actualiza el registro de attendance marcando attended=True.
    """
    sb = _sb()
    user_id = str(current_user["id"])
    
    parsed = validate_qr_token(payload.token)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código QR inválido o expirado"
        )
    
    event_id, _ = parsed
    
    event_response = sb.table("events").select("*").eq("id", event_id).execute()
    if not event_response.data or len(event_response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado"
        )
    
    event = event_response.data[0]
    
    if event.get("status") != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El evento no está disponible para registrar asistencia"
        )
    
    if not event.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El evento no está activo"
        )

    user_email = (current_user.get("email") or "").lower()
    email_domain = user_email.split("@")[-1] if "@" in user_email else ""
    access_type = (event.get("access_type") or event.get("audience") or "publico").lower()

    if access_type in ["public", "publico"]:
        pass
    elif access_type in ["puce_only", "interno"]:
        puce_domains = _normalize_list(PUCE_ALLOWED_DOMAINS)
        if not email_domain or email_domain not in puce_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este evento es exclusivo para PUCE. Inicia sesión con tu correo institucional para inscribirte."
            )
    elif access_type in ["interuniversity", "interuniversitario"]:
        allowed_domains = _normalize_list(event.get("allowed_domains"))
        allowed_emails = _normalize_list(event.get("allowed_emails"))
        if not allowed_domains and not allowed_emails:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este evento es interuniversitario pero aún no tiene universidades habilitadas. Contacta al administrador."
            )
        if user_email not in allowed_emails and email_domain not in allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este evento es interuniversitario. Tu universidad no está habilitada para inscribirse."
            )
    
    now_utc = datetime.now(timezone.utc)
    start_dt = _to_utc(event.get("start_date"))
    end_dt = _to_utc(event.get("end_date"))

    if start_dt:
        allowed_from = start_dt - timedelta(minutes=5)
        if now_utc < allowed_from:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La asistencia estará disponible 5 minutos antes del inicio del evento."
            )

    if end_dt:
        allowed_until = end_dt + timedelta(minutes=7)
        if now_utc > allowed_until:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El tiempo para registrar asistencia ya ha finalizado."
            )
    
    attendance_response = sb.table("attendances").select("*").eq("user_id", user_id).eq("event_id", event_id).execute()
    
    if not attendance_response.data or len(attendance_response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes estar inscrito en el evento para registrar asistencia"
        )
    
    attendance = attendance_response.data[0]
    
    if attendance.get("attended", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya registraste tu asistencia a este evento"
        )
    
    update_data = {
        "attended": True,
        "attended_at": now_utc.isoformat()
    }
    
    response = sb.table("attendances").update(update_data).eq("id", attendance["id"]).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar la asistencia"
        )
    
    return {
        "id": response.data[0]["id"],
        "event_id": event_id,
        "user_id": str(user_id),  # Asegurar que sea string
        "status": "attended",
        "attended_at": response.data[0].get("attended_at"),
        "created_at": attendance.get("created_at") or attendance.get("timestamp"),
    }


@router.get(
    "/event/{event_id}/list",
    response_model=list[AttendanceRead],
    summary="Listar asistencias de un evento",
)
async def list_event_attendances(
    event_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Lista todas las asistencias registradas para un evento.
    Solo el creador del evento o un admin puede ver las asistencias.
    """
    try:
        sb = _sb()
        
        event_response = sb.table("events").select("*").eq("id", event_id).execute()
        if not event_response.data or len(event_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento no encontrado"
            )
        
        event = event_response.data[0]
        user_role = (current_user.get("user_metadata") or {}).get("role") or current_user.get("role", "student")
        
        if str(event.get("creator_id")) != str(current_user["id"]) and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para ver las asistencias de este evento"
            )
        
        response = sb.table("attendances").select("*").eq("event_id", event_id).execute()
        
        attendances = []
        for att in (response.data or []):
            attendances.append({
                "id": att["id"],
                "event_id": att["event_id"],
                "user_id": str(att["user_id"]),  # Asegurar que sea string
                "status": "attended" if att.get("attended", False) else "enrolled",
                "attended_at": att.get("attended_at"),
                "created_at": att.get("created_at") or att.get("timestamp"),
            })
        
        return attendances
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar asistencias: {str(e)}"
        )


@router.get(
    "/admin/events/{event_id}/attendances",
    summary="Listar asistentes de un evento (admin)",
    dependencies=[Depends(require_admin)],
)
async def list_event_attendees_admin(event_id: int):
    """
    Lista asistentes (attended=True) con datos de usuario.
    Solo administradores.
    """
    try:
        sb = _sb()
        event_response = sb.table("events").select("id, title, capacity").eq("id", event_id).execute()
        if not event_response.data or len(event_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento no encontrado"
            )
        event = event_response.data[0]

        attendance_response = (
            sb.table("attendances")
            .select("id, user_id, attended, attended_at")
            .eq("event_id", event_id)
            .eq("attended", True)
            .execute()
        )
        rows = attendance_response.data or []
        user_ids = [row.get("user_id") for row in rows if row.get("user_id")]

        users_map = {}
        if user_ids:
            users_response = (
                sb.table("users")
                .select("id, names, surnames, email, role")
                .in_("id", user_ids)
                .execute()
            )
            for user in (users_response.data or []):
                full_name = f"{user.get('names', '')} {user.get('surnames', '')}".strip()
                users_map[user["id"]] = {
                    "name": full_name or "Sin nombre",
                    "email": user.get("email", ""),
                    "role": user.get("role", "")
                }

        attendees = []
        for row in rows:
            user = users_map.get(row.get("user_id"), {})
            attendees.append({
                "user_id": row.get("user_id"),
                "name": user.get("name"),
                "email": user.get("email"),
                "role": user.get("role"),
                "attended_at": row.get("attended_at")
            })

        return {
            "event_id": event_id,
            "event_title": event.get("title"),
            "capacity": event.get("capacity"),
            "total_attendees": len(attendees),
            "attendees": attendees
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar asistentes: {str(e)}"
        )


@router.get(
    "/my-attendances",
    response_model=list[AttendanceRead],
    summary="Listar mis asistencias",
)
async def list_my_attendances(current_user: dict = Depends(get_current_user)):
    """Lista todas las asistencias del usuario actual."""
    try:
        sb = _sb()
        response = sb.table("attendances").select("*").eq("user_id", current_user["id"]).execute()

        rows = response.data or []
        event_ids = [row.get("event_id") for row in rows if row.get("event_id") is not None]
        events_map = {}
        if event_ids:
            events_response = (
                sb.table("events")
                .select("id, title, start_date, end_date, location")
                .in_("id", event_ids)
                .execute()
            )
            for event in (events_response.data or []):
                events_map[event["id"]] = event
        
        attendances = []
        for att in rows:
            event = events_map.get(att.get("event_id"))
            attendances.append({
                "id": att["id"],
                "event_id": att["event_id"],
                "user_id": str(att["user_id"]),  # Asegurar que sea string
                "status": "attended" if att.get("attended", False) else "enrolled",
                "attended_at": att.get("attended_at"),
                "created_at": att.get("created_at") or att.get("timestamp"),
                "event_title": event.get("title") if event else None,
                "event_start_date": event.get("start_date") if event else None,
                "event_end_date": event.get("end_date") if event else None,
                "event_location": event.get("location") if event else None,
            })
        
        return attendances
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar asistencias: {str(e)}"
        )
