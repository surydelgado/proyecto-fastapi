from datetime import datetime
from pydantic import Field
from .base import APIModel, TimestampMixin


class MicrocredentialBase(APIModel):
    event_id: int
    user_id: int
    issued_at: datetime
    certificate_url: str | None = Field(default=None, max_length=500)
    verification_code: str = Field(min_length=10, max_length=120)


class MicrocredentialCreate(APIModel):
    event_id: int
    user_id: int


class MicrocredentialRead(MicrocredentialBase, TimestampMixin):
    id: int
