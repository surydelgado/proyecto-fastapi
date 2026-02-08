from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any
import resend

from app.auth import get_current_user
from app.config import supabase, supabase_admin
from app.services.email import RESEND_API_KEY, RESEND_FROM


router = APIRouter()


def _sb():
    return supabase_admin if supabase_admin else supabase


@router.get(
    "/notifications/mine",
    summary="Listar mis notificaciones",
)
async def list_my_notifications(current_user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    sb = _sb()
    user_id = current_user["id"]
    response = (
        sb.table("notifications")
        .select("id, title, message, link_url, type, is_read, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return response.data or []


@router.post(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Marcar notificación como leída",
)
async def mark_notification_read(notification_id: int, current_user: dict = Depends(get_current_user)):
    sb = _sb()
    user_id = current_user["id"]
    response = (
        sb.table("notifications")
        .update({"is_read": True})
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada")
    return {"status": "ok"}


@router.post(
    "/notifications/read-all",
    status_code=status.HTTP_200_OK,
    summary="Marcar todas las notificaciones como leídas",
)
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    sb = _sb()
    user_id = current_user["id"]
    sb.table("notifications").update({"is_read": True}).eq("user_id", user_id).execute()
    return {"status": "ok"}


@router.post(
    "/test-email",
    status_code=status.HTTP_200_OK,
    summary="Enviar correo de prueba",
)
async def send_test_email(to_email: str = "delgadosury.22@gmail.com"):
    """
    Endpoint para enviar un correo de prueba.
    """
    if not RESEND_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RESEND_API_KEY no está configurada"
        )
    
    if not to_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo de destino es requerido"
        )
    
    resend.api_key = RESEND_API_KEY
    
    html = """
    <div style="font-family:Arial,Helvetica,sans-serif;background-color:#f4f6fb;padding:24px;">
        <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e3e7f0;">
            <div style="background:#0c3c78;color:#ffffff;padding:20px 24px;">
                <div style="font-size:14px;letter-spacing:0.5px;text-transform:uppercase;">Proyecto Eventos</div>
                <h1 style="margin:6px 0 0;font-size:22px;">Correo de Prueba</h1>
            </div>
            <div style="padding:22px 24px;color:#1f2a44;">
                <p style="margin:0 0 12px;">Hola,</p>
                <p style="margin:0 0 12px;">Este es un correo de prueba para verificar la configuración del remitente.</p>
                <p style="margin:0 0 12px;">El remitente configurado es: <strong>Proyecto Eventos &lt;no-reply@proyectoeventos12.site&gt;</strong></p>
            </div>
            <div style="padding:14px 24px;background:#f2f5fb;color:#2a3d66;font-size:12px;">
                Si recibiste este correo, la configuración está funcionando correctamente.
            </div>
        </div>
    </div>
    """
    
    try:
        result = resend.Emails.send(
            {
                "from": RESEND_FROM,
                "to": to_email,
                "subject": "Correo de Prueba - Proyecto Eventos",
                "html": html,
            }
        )
        return {
            "status": "success",
            "message": f"Correo enviado exitosamente a {to_email}",
            "result": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al enviar correo: {str(e)}"
        )
