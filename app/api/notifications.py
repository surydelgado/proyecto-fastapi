from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any

from app.auth import get_current_user
from app.config import supabase, supabase_admin


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
