from datetime import datetime
from pydantic import Field
from .base import APIModel, TimestampMixin


class AttendanceBase(APIModel):
    event_id: int
    user_id: int
    attended_at: datetime | None = None


class AttendanceCreate(APIModel):
    """Schema para crear una asistencia usando código QR."""
    qr_token: str = Field(min_length=10, max_length=300)


class AttendanceRead(AttendanceBase, TimestampMixin):
    """Schema para leer información de asistencia."""
    id: int
    status: str  # "attended" o "pending" 





