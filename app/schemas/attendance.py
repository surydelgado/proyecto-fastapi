from datetime import datetime
from pydantic import Field
from .base import APIModel, TimestampMixin


class AttendanceBase(APIModel):
    event_id: int
    user_id: str  # UUID de Supabase Auth
    attended_at: datetime | None = None


class AttendanceCreate(APIModel):
    """Schema para crear una asistencia (ya no se usa directamente, se usa QRScanRequest)."""
    pass


class AttendanceRead(AttendanceBase, TimestampMixin):
    """Schema para leer información de asistencia."""
    id: int
    status: str  # "attended" o "pending" 
    event_title: str | None = None
    event_start_date: datetime | None = None
    event_end_date: datetime | None = None
    event_location: str | None = None





