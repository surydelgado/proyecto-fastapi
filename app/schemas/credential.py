from datetime import datetime
from pydantic import Field
from .base import APIModel


class CredentialMineRead(APIModel):
    event_id: int
    event_title: str | None = None
    issued_at: datetime | None = None
    status: str = Field(default="valid", pattern="^(valid|revoked)$")
    certificate_url: str | None = Field(default=None, max_length=500)
    verify_url: str | None = Field(default=None, max_length=500)
    credential_code: str | None = Field(default=None, max_length=120)
    folio: str | None = Field(default=None, max_length=120)


class CredentialIssueSummary(APIModel):
    total_attendees: int
    issued: int
    existing: int
    failed: int = 0
