from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, BackgroundTasks
from typing import Optional
from pathlib import Path
from uuid import uuid4
from pydantic import BaseModel, Field

from supabase import Client, create_client
from app.config import SUPABASE_KEY, SUPABASE_URL, supabase, supabase_admin, APP_BASE_URL
from app.schemas.event import EventCreate, EventRead, EventUpdate, EventValidated
from app.auth import get_current_user, require_admin
from app.services.email import send_cancellation_email


router = APIRouter()


def _admin_db(current_user: dict | None = None) -> Client:
    if supabase_admin:
        return supabase_admin
    token = (current_user or {}).get("access_token")
    if token:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        client.auth._headers["Authorization"] = f"Bearer {token}"
        return client
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="SUPABASE_SERVICE_KEY no está configurada en el servidor."
    )


def _user_db(current_user: dict | None = None) -> Client:
    token = (current_user or {}).get("access_token")
    if token:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        client.auth._headers["Authorization"] = f"Bearer {token}"
        return client
    return supabase


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


def _apply_finalized_status(event: dict, now_utc: datetime) -> dict:
    end_dt = _to_utc(event.get("end_date"))
    status = (event.get("status") or "").lower()
    if status == "approved" and end_dt and now_utc > end_dt:
        event["status"] = "finalized"
    return event


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
        "audience": payload.audience or "publico",
        "allowed_domains": payload.allowed_domains,
        "allowed_emails": payload.allowed_emails,
        "access_note": payload.access_note,
        "location": payload.location,
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "capacity": payload.capacity,
        "requires_certificate": payload.requires_certificate,
        "certificate_template": payload.certificate_template or "default",
        "certificate_title": payload.certificate_title,
        "certificate_signer_name": payload.certificate_signer_name,
        "certificate_signer_role": payload.certificate_signer_role,
        "certificate_signer_image_url": payload.certificate_signer_image_url,
        "requires_professor_signature": payload.requires_professor_signature,
        "certificate_professor_signer_name": payload.certificate_professor_signer_name,
        "certificate_professor_signer_role": payload.certificate_professor_signer_role,
        "certificate_professor_signer_image_url": payload.certificate_professor_signer_image_url,
        "certificate_background_url": payload.certificate_background_url,
        "status": "pending",
        "is_active": True,
        "creator_id": current_user["id"],
    }
    
    try:
        db_client = _admin_db(current_user)
        response = db_client.table("events").insert(event_data).execute()
        
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
    Incluye información del creador cuando está disponible.
    """
    query = supabase.table("events").select("*")
    
    if not include_inactive:
        query = query.eq("is_active", True)
    
    if status:
        if status == "finalized":
            query = query.eq("status", "approved")
        else:
            query = query.eq("status", status)
    
    query = query.order("created_at", desc=True).range(skip, skip + limit - 1)
    
    try:
        response = query.execute()
        events = response.data or []
        now_utc = datetime.now(timezone.utc)
        
        # Obtener información de los creadores
        creator_ids = [event.get("creator_id") for event in events if event.get("creator_id")]
        
        creators_map = {}
        if creator_ids:
            try:
                client = supabase_admin or supabase
                users_response = (
                    client.table("users")
                    .select("id, names, surnames, email")
                    .in_("id", creator_ids)
                    .execute()
                )
                
                for user in users_response.data or []:
                    creator_name = f"{user.get('names', '')} {user.get('surnames', '')}".strip()
                    creators_map[user["id"]] = {
                        "name": creator_name or "Sin nombre",
                        "email": user.get("email", "")
                    }
            except Exception:
                pass  # Si hay error, continuar sin información del creador
        
        # Agregar información del creador a cada evento
        for event in events:
            _apply_finalized_status(event, now_utc)
            creator_id = event.get("creator_id")
            if creator_id and creator_id in creators_map:
                creator = creators_map[creator_id]
                event["creator_name"] = creator["name"]
                event["creator_email"] = creator["email"]
            elif creator_id:
                event["creator_name"] = "Usuario eliminado"
                event["creator_email"] = ""
            else:
                event["creator_name"] = None
                event["creator_email"] = None
        
        if status == "finalized":
            events = [event for event in events if (event.get("status") or "").lower() == "finalized"]
        elif status == "approved":
            events = [event for event in events if (event.get("status") or "").lower() == "approved"]

        return events
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
        events = response.data or []
        now_utc = datetime.now(timezone.utc)
        for event in events:
            _apply_finalized_status(event, now_utc)
        return events
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
    Incluye información del creador del evento.
    """
    try:
        # Obtener eventos pendientes
        response = (
            supabase.table("events")
            .select("*")
            .eq("status", "pending")
            .eq("is_active", True)
            .order("created_at", desc=True)
            .execute()
        )
        
        events = response.data or []
        now_utc = datetime.now(timezone.utc)
        
        # Obtener información de los creadores
        creator_ids = [event.get("creator_id") for event in events if event.get("creator_id")]
        
        creators_map = {}
        if creator_ids:
            # Obtener todos los usuarios creadores en una sola consulta
            client = supabase_admin or supabase
            users_response = (
                client.table("users")
                .select("id, names, surnames, email")
                .in_("id", creator_ids)
                .execute()
            )
            
            for user in users_response.data or []:
                creator_name = f"{user.get('names', '')} {user.get('surnames', '')}".strip()
                creators_map[user["id"]] = {
                    "name": creator_name or "Sin nombre",
                    "email": user.get("email", "")
                }
        
        # Agregar información del creador a cada evento
        for event in events:
            _apply_finalized_status(event, now_utc)
            creator_id = event.get("creator_id")
            if creator_id and creator_id in creators_map:
                creator = creators_map[creator_id]
                event["creator_name"] = creator["name"]
                event["creator_email"] = creator["email"]
            else:
                event["creator_name"] = "Usuario eliminado"
                event["creator_email"] = ""
        
        return events
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
    Incluye información del creador si está disponible.
    """
    event = _get_event_or_404(event_id)
    _apply_finalized_status(event, datetime.now(timezone.utc))
    
    # Obtener información del creador si existe
    creator_id = event.get("creator_id")
    if creator_id:
        try:
            client = supabase_admin or supabase
            user_response = (
                client.table("users")
                .select("id, names, surnames, email")
                .eq("id", creator_id)
                .execute()
            )
            
            if user_response.data and len(user_response.data) > 0:
                user = user_response.data[0]
                creator_name = f"{user.get('names', '')} {user.get('surnames', '')}".strip()
                event["creator_name"] = creator_name or "Sin nombre"
                event["creator_email"] = user.get("email", "")
            else:
                event["creator_name"] = "Usuario eliminado"
                event["creator_email"] = ""
        except Exception:
            # Si hay error al obtener el usuario, continuar sin esa información
            event["creator_name"] = "No disponible"
            event["creator_email"] = ""
    else:
        event["creator_name"] = "No especificado"
        event["creator_email"] = ""
    
    return event


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
        response = _user_db(current_user).table("events").update(data).eq("id", event_id).execute()
        
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


@router.post(
    "/{event_id}/signature",
    response_model=EventRead,
    summary="Subir firma institucional del certificado",
)
async def upload_event_signature(
    event_id: int,
    file: UploadFile = File(...),
    signer_name: str | None = Form(default=None),
    signer_role: str | None = Form(default=None),
    current_user: dict = Depends(require_admin),
):
    event = _get_event_or_404(event_id)

    if not event.get("requires_certificate", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El evento no requiere microcredenciales",
        )

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no permitido. Usa JPG, PNG o WebP.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío",
        )

    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".png"

    file_path = f"event-signatures/event_{event_id}/institutional_{uuid4().hex}{extension}"
    bucket_name = "eventos"
    storage_client = _admin_db(current_user)
    content_type = file.content_type or "application/octet-stream"

    try:
        storage_client.storage.from_(bucket_name).upload(
            file_path,
            file_bytes,
            file_options={"content-type": str(content_type), "upsert": "true"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir la firma: {str(e)}",
        )

    public_url = storage_client.storage.from_(bucket_name).get_public_url(file_path)
    if isinstance(public_url, dict):
        public_url = (
            public_url.get("publicUrl")
            or public_url.get("public_url")
            or (public_url.get("data") or {}).get("publicUrl")
            or (public_url.get("data") or {}).get("public_url")
        )

    if not public_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener la URL pública de la firma",
        )

    update_data = {"certificate_signer_image_url": public_url}
    if signer_name is not None:
        update_data["certificate_signer_name"] = signer_name
    if signer_role is not None:
        update_data["certificate_signer_role"] = signer_role

    try:
        response = (
            _admin_db(current_user).table("events")
            .update(update_data)
            .eq("id", event_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo actualizar la firma institucional",
            )
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar la firma: {str(e)}",
        )


@router.post(
    "/{event_id}/professor-signature",
    response_model=EventRead,
    summary="Subir firma del profesor/ponente",
)
async def upload_professor_signature(
    event_id: int,
    file: UploadFile = File(...),
    professor_name: str | None = Form(default=None),
    professor_role: str | None = Form(default=None),
    current_user: dict = Depends(get_current_user),
):
    event = _get_event_or_404(event_id)

    user_role = current_user.get("role") or current_user.get("user_metadata", {}).get("role", "student")
    if event.get("creator_id") != current_user.get("id") and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para subir la firma del profesor",
        )

    if not event.get("requires_certificate", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El evento no requiere microcredenciales",
        )

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no permitido. Usa JPG, PNG o WebP.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío",
        )

    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".png"

    file_path = f"event-signatures/event_{event_id}/professor_{uuid4().hex}{extension}"
    bucket_name = "eventos"
    storage_client = _admin_db(current_user)
    content_type = file.content_type or "application/octet-stream"

    try:
        storage_client.storage.from_(bucket_name).upload(
            file_path,
            file_bytes,
            file_options={"content-type": str(content_type), "upsert": "true"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir la firma: {str(e)}",
        )

    public_url = storage_client.storage.from_(bucket_name).get_public_url(file_path)
    if isinstance(public_url, dict):
        public_url = (
            public_url.get("publicUrl")
            or public_url.get("public_url")
            or (public_url.get("data") or {}).get("publicUrl")
            or (public_url.get("data") or {}).get("public_url")
        )

    if not public_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener la URL pública de la firma",
        )

    update_data = {
        "certificate_professor_signer_image_url": public_url,
        "requires_professor_signature": True,
    }
    if professor_name is not None:
        update_data["certificate_professor_signer_name"] = professor_name
    if professor_role is not None:
        update_data["certificate_professor_signer_role"] = professor_role

    try:
        response = (
            _admin_db(current_user).table("events")
            .update(update_data)
            .eq("id", event_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo actualizar la firma del profesor",
            )
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar la firma: {str(e)}",
        )


@router.post(
    "/{event_id}/cover-image",
    response_model=EventRead,
    summary="Subir imagen de portada del evento",
)
async def upload_event_cover_image(
    event_id: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Permite a docentes/admin subir la imagen de portada de un evento aprobado.
    """
    event = _get_event_or_404(event_id)

    # Obtener rol real desde la base de datos si es posible
    user_role = current_user.get("role") or current_user.get("user_metadata", {}).get("role", "student")
    user_db_response = supabase.table("users").select("role").eq("id", current_user["id"]).execute()
    if user_db_response.data and len(user_db_response.data) > 0:
        user_role = user_db_response.data[0].get("role", user_role)

    if user_role not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para subir portada",
        )

    if event.get("creator_id") != current_user["id"] and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el creador o un admin puede subir la portada",
        )

    if event.get("status") != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La portada solo se puede subir cuando el evento está aprobado",
        )

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no permitido. Usa JPG, PNG o WebP.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío",
        )

    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".jpg"

    file_path = f"event-covers/event_{event_id}/{uuid4().hex}{extension}"
    bucket_name = "eventos"
    storage_client = _admin_db(current_user)

    content_type = file.content_type or "application/octet-stream"
    try:
        storage_client.storage.from_(bucket_name).upload(
            file_path,
            file_bytes,
            file_options={"content-type": str(content_type), "upsert": "true"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir la imagen: {str(e)}",
        )

    public_url = storage_client.storage.from_(bucket_name).get_public_url(file_path)
    if isinstance(public_url, dict):
        public_url = (
            public_url.get("publicUrl")
            or public_url.get("public_url")
            or (public_url.get("data") or {}).get("publicUrl")
            or (public_url.get("data") or {}).get("public_url")
        )

    if not public_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener la URL pública de la portada",
        )

    try:
        response = (
            _admin_db(current_user).table("events")
            .update({"cover_image_url": public_url})
            .eq("id", event_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo actualizar la portada del evento",
            )
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar la portada: {str(e)}",
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
            _user_db(current_user).table("events").delete().eq("id", event_id).execute()
        else:
            # Eliminación lógica
            _user_db(current_user).table("events").update({"is_active": False}).eq("id", event_id).execute()
        
        return None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar el evento: {str(e)}"
        )


@router.patch(
    "/{event_id}/approve",
    response_model=EventRead,
    summary="Aprobar un evento"
)
async def approve_event(
    event_id: int,
    current_user: dict = Depends(require_admin)
):
    """
    Aprueba un evento cambiando su estado a "approved".
    Solo accesible para administradores.
    """
    event = _get_event_or_404(event_id)
    
    try:
        response = _admin_db(current_user).table("events").update({"status": "approved"}).eq("id", event_id).execute()
        
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
    summary="Rechazar un evento"
)
async def reject_event(
    event_id: int,
    current_user: dict = Depends(require_admin)
):
    """
    Rechaza un evento cambiando su estado a "denied".
    Solo accesible para administradores.
    """
    event = _get_event_or_404(event_id)
    
    try:
        response = _admin_db(current_user).table("events").update({"status": "denied"}).eq("id", event_id).execute()
        
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
    CANCELLED = "cancelled"


class EventStatusUpdate(BaseModel):
    status: EventStatus


def _notify_cancelled_event(event_id: int, event: dict):
    """
    Envía notificaciones y correos a todos los usuarios inscritos cuando un evento se cancela.
    Esta función se ejecuta en background.
    """
    logger = logging.getLogger(__name__)
    try:
        # Obtener todos los usuarios inscritos en el evento
        attendances_response = supabase_admin.table("attendances").select("user_id").eq("event_id", event_id).execute()
        
        if not attendances_response.data or len(attendances_response.data) == 0:
            return  # No hay usuarios inscritos
        
        user_ids = [attendance["user_id"] for attendance in attendances_response.data]
        
        # Obtener información de los usuarios
        users_response = supabase_admin.table("users").select("id, names, surnames, email").in_("id", user_ids).execute()
        
        if not users_response.data:
            return
        
        # Preparar información del evento para el correo
        event_title = event.get("title") or "Evento académico"
        event_location = event.get("location") or "Por confirmar"
        
        # Formatear fecha del evento
        event_date_str = None
        if event.get("start_date"):
            try:
                start_dt = _to_utc(event.get("start_date"))
                if start_dt:
                    # Convertir a zona horaria local (Ecuador)
                    from zoneinfo import ZoneInfo
                    try:
                        local_tz = ZoneInfo("America/Guayaquil")
                    except:
                        from datetime import timedelta
                        local_tz = timezone(timedelta(hours=-5))
                    
                    local_dt = start_dt.astimezone(local_tz)
                    months_es = [
                        "enero", "febrero", "marzo", "abril", "mayo", "junio",
                        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
                    ]
                    event_date_str = f"{local_dt.day} de {months_es[local_dt.month - 1]} de {local_dt.year} a las {local_dt.strftime('%H:%M')}"
            except Exception:
                pass
        
        # Crear notificaciones y enviar correos para cada usuario
        for user in users_response.data:
            user_id = user.get("id")
            user_email = user.get("email")
            user_names = user.get("names", "")
            user_surnames = user.get("surnames", "")
            full_name = f"{user_names} {user_surnames}".strip() or "participante"
            
            # Crear notificación
            try:
                supabase_admin.table("notifications").insert({
                    "user_id": user_id,
                    "title": "Evento cancelado",
                    "message": f"El evento '{event_title}' ha sido cancelado.",
                    "link_url": f"{APP_BASE_URL}/dashboard" if APP_BASE_URL else None,
                    "type": "event_cancelled",
                    "is_read": False,
                }).execute()
            except Exception as e:
                logger.warning(f"Error al crear notificación para usuario {user_id}: {str(e)}")
            
            # Enviar correo
            if user_email:
                try:
                    send_cancellation_email(
                        to_email=user_email,
                        full_name=full_name,
                        event_title=event_title,
                        event_date=event_date_str,
                        event_location=event_location,
                    )
                except Exception as e:
                    logger.warning(f"Error al enviar correo de cancelación a {user_email}: {str(e)}")
    
    except Exception as e:
        logger.exception(f"Error al notificar cancelación del evento {event_id}: {str(e)}")


@router.patch(
    "/{event_id}/status",
    response_model=EventRead,
    summary="Cambiar estado de un evento"
)
async def change_event_status(
    event_id: int,
    payload: EventStatusUpdate,
    background: BackgroundTasks,
    current_user: dict = Depends(require_admin)
):
    """
    Cambia el estado de un evento a "approved", "finalized" o "cancelled".
    Solo accesible para administradores.
    Si se cancela el evento, se envían notificaciones y correos a los usuarios inscritos.
    """
    event = _get_event_or_404(event_id)
    old_status = event.get("status", "").lower()
    
    try:
        response = _admin_db(current_user).table("events").update({"status": payload.status.value}).eq("id", event_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al cambiar el estado del evento"
            )
        
        updated_event = response.data[0]
        
        # Si el evento se cancela, enviar notificaciones y correos a los usuarios inscritos
        if payload.status.value == "cancelled" and old_status != "cancelled":
            background.add_task(
                _notify_cancelled_event,
                event_id,
                updated_event
            )
        
        return updated_event
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al cambiar el estado del evento: {str(e)}"
        )
