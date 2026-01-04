from datetime import datetime
from pydantic import Field
from .base import APIModel, TimestampMixin



class AttendanceBase(APIModel):
    event_id: int
    user_id: int
    attended_at: datetime | None = None

# esto funciona para la asitencia del QR
class AttendanceCreate(APIModel):
    qr_token: str = Field(min_length=10, max_length=300)


class AttendanceRead(AttendanceBase, TimestampMixin):
    id: int
    status: str 





