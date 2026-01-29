"""
API de gestión de asistencia a eventos usando Supabase.
"""
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from typing import Optional

from app.config import supabase, supabase_admin, APP_BASE_URL
from app.schemas.attendance import AttendanceCreate, AttendanceRead
from app.auth import get_current_user
from app.services.qr_service import generate_qr_png_bytes
from app.services.qr_token_service import generate_qr_token


router = APIRouter()


def _sb():
    """Cliente con permisos para leer/escribir (evita RLS desde backend)."""
    return supabase_admin if supabase_admin else supabase


@router.post(
    "/enroll/{event_id}",
    response_model=AttendanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Inscribirse a un evento aprobado",
)
async def enroll_to_event(
    event_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Inscribe al usuario actual a un evento aprobado.
    Requiere autenticación. El evento debe estar aprobado y activo.
    """
    try:
        sb = _sb()
        user_id = str(current_user["id"])

        event_response = sb.table("events").select("*").eq("id", event_id).execute()
        if not event_response.data or len(event_response.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado")
        event = event_response.data[0]

        if event.get("status") != "approved":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo puedes inscribirte a eventos aprobados")
        if not event.get("is_active", False):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El evento no está activo")

        if event.get("capacity"):
            count_response = sb.table("attendances").select("id", count="exact").eq("event_id", event_id).execute()
            current_count = count_response.count if hasattr(count_response, "count") else len(count_response.data or [])
            if current_count >= event["capacity"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El evento ha alcanzado su capacidad máxima")

        existing_response = sb.table("attendances").select("*").eq("user_id", user_id).eq("event_id", event_id).execute()
        if existing_response.data and len(existing_response.data) > 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya estás inscrito en este evento")

        qr_code = secrets.token_urlsafe(32)
        attendance_data = {"user_id": user_id, "event_id": event_id, "qr_code": qr_code, "attended": False}
        response = sb.table("attendances").insert(attendance_data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al inscribirse al evento")

        row = response.data[0]
        return {
            "id": row["id"],
            "event_id": event_id,
            "user_id": user_id,
            "status": "enrolled",
            "attended_at": None,
            "created_at": row.get("created_at") or row.get("timestamp"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al inscribirse al evento: {str(e)}")


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
            return {"enrolled": True, "attendance_id": response.data[0]["id"], "attended": response.data[0].get("attended", False)}
        return {"enrolled": False, "attendance_id": None, "attended": False}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al verificar inscripción: {str(e)}")


@router.post(
    "/generate-qr/{event_id}",
    summary="Generar código QR para un evento",
)
async def generate_qr_code(
    event_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Genera un código QR único para que un usuario pueda asistir a un evento.
    Requiere autenticación.
    """
    try:
        # Verificar que el evento existe
        event_response = supabase.table("events").select("*").eq("id", event_id).execute()
        
        if not event_response.data or len(event_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento no encontrado"
            )
        
        event = event_response.data[0]
        
        # Verificar que el evento está activo
        if not event.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El evento no está activo"
            )
        
        # Generar código QR único
        qr_code = secrets.token_urlsafe(32)
        
        # Crear registro de asistencia
        attendance_data = {
            "user_id": current_user["id"],
            "event_id": event_id,
            "qr_code": qr_code,
            "attended": False,
        }
        
        response = supabase.table("attendances").insert(attendance_data).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al generar el código QR"
            )
        
        return {
            "qr_code": qr_code,
            "qr_token": qr_code,  # Alias para compatibilidad
            "event_id": event_id,
            "attendance_id": response.data[0]["id"],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar código QR: {str(e)}"
        )


@router.post(
    "/register",
    response_model=AttendanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar asistencia usando código QR",
)
async def register_attendance(
    payload: AttendanceCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Registra la asistencia de un usuario a un evento usando el código QR.
    Requiere autenticación.
    """
    try:
        # Buscar el registro de asistencia por código QR
        attendance_response = supabase.table("attendances").select("*").eq("qr_code", payload.qr_token).execute()
        
        if not attendance_response.data or len(attendance_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Código QR inválido o expirado"
            )
        
        attendance = attendance_response.data[0]
        
        # Verificar que el código QR pertenece al usuario actual o el usuario es admin
        user_role = current_user.get("user_metadata", {}).get("role", "student")
        
        if attendance["user_id"] != current_user["id"] and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este código QR no pertenece a tu cuenta"
            )
        
        # Verificar que no haya asistido ya
        if attendance.get("attended", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya se registró la asistencia para este evento"
            )
        
        # Verificar que el evento existe y está activo
        event_response = supabase.table("events").select("*").eq("id", attendance["event_id"]).execute()
        
        if not event_response.data or len(event_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento no encontrado"
            )
        
        event = event_response.data[0]
        
        if not event.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El evento no está activo"
            )
        
        # Actualizar asistencia
        update_data = {
            "attended": True,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        response = supabase.table("attendances").update(update_data).eq("id", attendance["id"]).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al registrar la asistencia"
            )
        
        return {
            "id": response.data[0]["id"],
            "event_id": attendance["event_id"],
            "user_id": attendance["user_id"],
            "status": "attended",
            "attended_at": response.data[0].get("timestamp"),
            "created_at": attendance.get("created_at"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar asistencia: {str(e)}"
        )


@router.get(
    "/event/{event_id}/qr-image",
    summary="Imagen QR del evento para registrar asistencia (formulario público)",
)
async def get_event_qr_image(
    request: Request,
    event_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Devuelve una imagen PNG del QR que apunta a /qr/asistencia?token=...
    Usa APP_BASE_URL si está configurado (para celular); si no, usa la URL de la petición para que el QR siempre se muestre.
    """
    sb = supabase_admin or supabase
    event_response = sb.table("events").select("*").eq("id", event_id).execute()
    if not event_response.data or len(event_response.data) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado")
    event = event_response.data[0]
    user_role = (current_user.get("user_metadata") or {}).get("role") or current_user.get("role", "student")
    if str(event.get("creator_id")) != str(current_user["id"]) and user_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el creador o un admin pueden ver este QR")
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
    url = f"{base}/qr/asistencia?token={token}"
    png_bytes = generate_qr_png_bytes(url)
    return Response(content=png_bytes, media_type="image/png")


@router.get(
    "/event/{event_id}",
    response_model=list[AttendanceRead],
    summary="Listar asistencias de un evento",
)
async def list_event_attendances(
    event_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Lista todas las asistencias registradas para un evento.
    Requiere autenticación. Solo el creador del evento o un admin puede ver las asistencias.
    """
    try:
        # Verificar que el evento existe
        event_response = supabase.table("events").select("*").eq("id", event_id).execute()
        
        if not event_response.data or len(event_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento no encontrado"
            )
        
        event = event_response.data[0]
        user_role = current_user.get("user_metadata", {}).get("role", "student")
        
        # Verificar permisos
        if event.get("creator_id") != current_user["id"] and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para ver las asistencias de este evento"
            )
        
        # Obtener asistencias
        response = supabase.table("attendances").select("*").eq("event_id", event_id).execute()
        
        attendances = []
        for att in (response.data or []):
            attendances.append({
                "id": att["id"],
                "event_id": att["event_id"],
                "user_id": att["user_id"],
                "status": "attended" if att.get("attended", False) else "pending",
                "attended_at": att.get("timestamp"),
                "created_at": att.get("created_at"),
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
    "/my-attendances",
    response_model=list[AttendanceRead],
    summary="Listar mis asistencias",
)
async def list_my_attendances(current_user: dict = Depends(get_current_user)):
    """
    Lista todas las asistencias del usuario actual.
    """
    try:
        response = supabase.table("attendances").select("*").eq("user_id", current_user["id"]).execute()
        
        attendances = []
        for att in (response.data or []):
            attendances.append({
                "id": att["id"],
                "event_id": att["event_id"],
                "user_id": att["user_id"],
                "status": "attended" if att.get("attended", False) else "pending",
                "attended_at": att.get("timestamp"),
                "created_at": att.get("created_at"),
            })
        
        return attendances
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar asistencias: {str(e)}"
        )
