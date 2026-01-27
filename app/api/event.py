from __future__ import annotations

from datetime import datetime
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from pydantic import BaseModel, Field

from app.config import supabase, supabase_admin
from app.schemas.event import EventCreate, EventRead, EventUpdate, EventValidated
from app.auth import get_current_user, require_admin


router = APIRouter()


def _get_event_or_404(event_id: int) -> dict:
    """
    Obtiene un evento por ID desde Supabase.
    
    Raises:
        HTTPException: Si el evento no existe
    """
    response = supabase.table("events").select("*").eq("id", event_id).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado"
        )
    
    return response.data[0]


@router.post(
    "/",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un evento académico",
)
async def create_event(
    payload: EventCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Crea un nuevo evento académico.
    Requiere autenticación.
    """
    # Validación de fechas (end_date >= start_date)
    EventValidated(**payload.model_dump())
    
    # Obtener el rol del usuario desde la base de datos
    user_role = current_user.get("role") or current_user.get("user_metadata", {}).get("role", "student")
    user_db_response = supabase.table("users").select("role").eq("id", current_user["id"]).execute()
    if user_db_response.data and len(user_db_response.data) > 0:
        user_role = user_db_response.data[0].get("role", user_role)

    if user_role not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para proponer eventos",
        )
    
    # Preparar datos para insertar
    event_data = {
        "title": payload.title,
        "description": payload.description,
        "event_type": payload.event_type,
        "location": payload.location,
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "capacity": payload.capacity,
        "status": "pending",
        "is_active": True,
        "creator_id": current_user["id"],
    }
    
    try:
        response = supabase.table("events").insert(event_data).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al crear el evento"
            )
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear el evento: {str(e)}"
        )


@router.get(
    "/",
    response_model=list[EventRead],
    summary="Listar eventos",
)
async def list_events(
    skip: int = 0,
    limit: int = 50,
    include_inactive: bool = False,
    status: Optional[str] = None,
):
    """
    Lista eventos académicos.
    Por defecto solo muestra eventos activos.
    Puede filtrar por estado (pending, approved, denied, finalized).
    """
    query = supabase.table("events").select("*")
    
    if not include_inactive:
        query = query.eq("is_active", True)
    
    if status:
        query = query.eq("status", status)
    
    query = query.order("created_at", desc=True).range(skip, skip + limit - 1)
    
    try:
        response = query.execute()
        return response.data or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar eventos: {str(e)}"
        )


@router.get(
    "/approved",
    response_model=list[EventRead],
    summary="Listar eventos aprobados",
)
async def list_approved_events():
    """
    Lista todos los eventos aprobados disponibles para inscripción.
    Público, no requiere autenticación.
    """
    try:
        client = supabase_admin or supabase
        response = (
            client.table("events")
            .select("*")
            .eq("status", "approved")
            .eq("is_active", True)
            .order("start_date", desc=False)
            .execute()
        )
        return response.data or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar eventos aprobados: {str(e)}"
        )


@router.get(
    "/approved/list",
    response_model=list[EventRead],
    summary="Listar eventos aprobados (lista)",
)
async def list_approved_events_list():
    """
    Lista todos los eventos aprobados disponibles para inscripción.
    Ruta alternativa para evitar colisiones con /{event_id}.
    """
    return await list_approved_events()


@router.get(
    "/pending/list",
    response_model=list[EventRead],
    summary="Listar eventos pendientes",
    dependencies=[Depends(require_admin)]
)
async def list_pending_events():
    """
    Lista todos los eventos pendientes de aprobación.
    Solo accesible para administradores.
    """
    try:
        response = supabase.table("events").select("*").eq("status", "pending").eq("is_active", True).order("created_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar eventos pendientes: {str(e)}"
        )


@router.get(
    "/{event_id}",
    response_model=EventRead,
    summary="Obtener un evento por ID",
)
async def get_event(event_id: int):
    """
    Obtiene un evento específico por su ID.
    """
    return _get_event_or_404(event_id)


@router.put(
    "/{event_id}",
    response_model=EventRead,
    summary="Actualizar un evento",
)
async def update_event(
    event_id: int,
    payload: EventUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Actualiza un evento existente.
    Requiere autenticación. Solo el creador o un admin puede actualizar.
    """
    event = _get_event_or_404(event_id)
    
    # Verificar permisos: solo el creador o admin puede actualizar
    if event.get("creator_id") != current_user["id"]:
        user_role = current_user.get("user_metadata", {}).get("role", "student")
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para actualizar este evento"
            )
    
    # Preparar datos para actualizar
    data = payload.model_dump(exclude_unset=True)
    
    # Si se actualizan fechas, validarlas
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    
    if start_date or end_date:
        start_date = start_date or event["start_date"]
        end_date = end_date or event["end_date"]
        
        # Convertir strings a datetime si es necesario
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        
        EventValidated(
            title=data.get("title", event["title"]),
            description=data.get("description", event.get("description")),
            location=data.get("location", event.get("location")),
            start_date=start_date,
            end_date=end_date,
            capacity=data.get("capacity", event.get("capacity")),
        )
    
    # Convertir fechas a ISO si están presentes
    if "start_date" in data and isinstance(data["start_date"], datetime):
        data["start_date"] = data["start_date"].isoformat()
    if "end_date" in data and isinstance(data["end_date"], datetime):
        data["end_date"] = data["end_date"].isoformat()
    
    try:
        response = supabase.table("events").update(data).eq("id", event_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al actualizar el evento"
            )
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el evento: {str(e)}"
        )


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un evento",
)
async def delete_event(
    event_id: int,
    hard: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina un evento.
    
    - Por defecto: eliminación lógica (is_active=False)
    - hard=true: eliminación física (DELETE)
    
    Requiere autenticación. Solo el creador o un admin puede eliminar.
    """
    event = _get_event_or_404(event_id)
    
    # Verificar permisos
    if event.get("creator_id") != current_user["id"]:
        user_role = current_user.get("user_metadata", {}).get("role", "student")
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para eliminar este evento"
            )
    
    try:
        if hard:
            # Eliminación física
            supabase.table("events").delete().eq("id", event_id).execute()
        else:
            # Eliminación lógica
            supabase.table("events").update({"is_active": False}).eq("id", event_id).execute()
        
        return None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar el evento: {str(e)}"
        )


@router.patch(
    "/{event_id}/approve",
    response_model=EventRead,
    summary="Aprobar un evento",
    dependencies=[Depends(require_admin)]
)
async def approve_event(event_id: int):
    """
    Aprueba un evento cambiando su estado a "approved".
    Solo accesible para administradores.
    """
    event = _get_event_or_404(event_id)
    
    try:
        response = supabase.table("events").update({"status": "approved"}).eq("id", event_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al aprobar el evento"
            )
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al aprobar el evento: {str(e)}"
        )


@router.patch(
    "/{event_id}/reject",
    response_model=EventRead,
    summary="Rechazar un evento",
    dependencies=[Depends(require_admin)]
)
async def reject_event(event_id: int):
    """
    Rechaza un evento cambiando su estado a "denied".
    Solo accesible para administradores.
    """
    event = _get_event_or_404(event_id)
    
    try:
        response = supabase.table("events").update({"status": "denied"}).eq("id", event_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al rechazar el evento"
            )
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al rechazar el evento: {str(e)}"
        )


class EventStatus(str, Enum):
    APPROVED = "approved"
    FINALIZED = "finalized"


class EventStatusUpdate(BaseModel):
    status: EventStatus


@router.patch(
    "/{event_id}/status",
    response_model=EventRead,
    summary="Cambiar estado de un evento",
    dependencies=[Depends(require_admin)]
)
async def change_event_status(
    event_id: int,
    payload: EventStatusUpdate
):
    """
    Cambia el estado de un evento a "approved" o "finalized".
    Solo accesible para administradores.
    """
    event = _get_event_or_404(event_id)
    
    try:
        response = supabase.table("events").update({"status": payload.status.value}).eq("id", event_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al cambiar el estado del evento"
            )
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al cambiar el estado del evento: {str(e)}"
        )
