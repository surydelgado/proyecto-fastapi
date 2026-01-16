from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.session import get_db
from app import models
from app.schemas.event import EventCreate, EventRead, EventUpdate, EventValidated


router = APIRouter()


def _get_event_or_404(db: Session, event_id: int) -> models.Event:
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return event


@router.post(
    "/",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un evento académico",
)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    # Validación de fechas (ends_at >= starts_at)
    EventValidated(**payload.model_dump())

    event = models.Event(
        title=payload.title,
        description=payload.description,
        location=payload.location,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        capacity=payload.capacity,
        is_active=True,
    )

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get(
    "/",
    response_model=list[EventRead],
    summary="Listar eventos",
)
def list_events(
    skip: int = 0,
    limit: int = 50,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(models.Event)
    if not include_inactive:
        q = q.filter(models.Event.is_active == True)  # noqa: E712
    return q.order_by(models.Event.start_date.desc()).offset(skip).limit(limit).all()



@router.get(
    "/{event_id}",
    response_model=EventRead,
    summary="Obtener un evento por ID",
)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return _get_event_or_404(db, event_id)


@router.put(
    "/{event_id}",
    response_model=EventRead,
    summary="Actualizar un evento",
)
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)):
    event = _get_event_or_404(db, event_id)

    data = payload.model_dump(exclude_unset=True)

    # Si mandan fechas, validarlas en conjunto
    starts_at = data.get("starts_at", event.starts_at)
    ends_at = data.get("ends_at", event.ends_at)
    EventValidated(
        title=data.get("title", event.title),
        description=data.get("description", event.description),
        location=data.get("location", event.location),
        starts_at=starts_at,
        ends_at=ends_at,
        capacity=data.get("capacity", event.capacity),
    )

    for k, v in data.items():
        setattr(event, k, v)

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un evento",
)
def delete_event(event_id: int, hard: bool = False, db: Session = Depends(get_db)):
    """Eliminación del evento.

    - Por defecto: eliminación lógica (is_active=False)
    - hard=true: eliminación física (DELETE)
    """

    event = _get_event_or_404(db, event_id)

    if hard:
        db.delete(event)
    else:
        event.is_active = False
        db.add(event)

    db.commit()
    return None
