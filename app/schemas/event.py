from datetime import datetime
from pydantic import Field, model_validator
from .base import APIModel, TimestampMixin


class EventBase(APIModel):
    title: str = Field(min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    event_type: str | None = Field(default=None, max_length=100)
    audience: str | None = Field(default="publico", pattern="^(interno|interuniversitario|publico)$")
    allowed_domains: list[str] | None = None
    allowed_emails: list[str] | None = None
    access_note: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)
    start_date: datetime
    end_date: datetime
    capacity: int | None = Field(default=None, ge=1)
    requires_certificate: bool = False
    certificate_template: str | None = Field(default="default", max_length=100)
    certificate_title: str | None = Field(default=None, max_length=200)
    certificate_signer_name: str | None = Field(default=None, max_length=200)
    certificate_signer_role: str | None = Field(default=None, max_length=200)
    certificate_signer_image_url: str | None = Field(default=None, max_length=500)
    requires_professor_signature: bool = False
    certificate_professor_signer_name: str | None = Field(default=None, max_length=200)
    certificate_professor_signer_role: str | None = Field(default=None, max_length=200)
    certificate_professor_signer_image_url: str | None = Field(default=None, max_length=500)
    certificate_background_url: str | None = Field(default=None, max_length=500)


class EventCreate(EventBase):
    pass


class EventUpdate(APIModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    audience: str | None = Field(default=None, pattern="^(interno|interuniversitario|publico)$")
    allowed_domains: list[str] | None = None
    allowed_emails: list[str] | None = None
    access_note: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)
    start_date: datetime | None = None
    end_date: datetime | None = None
    capacity: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, pattern="^(pending|approved|denied|finalized)$")
    requires_certificate: bool | None = None
    certificate_template: str | None = Field(default=None, max_length=100)
    certificate_title: str | None = Field(default=None, max_length=200)
    certificate_signer_name: str | None = Field(default=None, max_length=200)
    certificate_signer_role: str | None = Field(default=None, max_length=200)
    certificate_signer_image_url: str | None = Field(default=None, max_length=500)
    requires_professor_signature: bool | None = None
    certificate_professor_signer_name: str | None = Field(default=None, max_length=200)
    certificate_professor_signer_role: str | None = Field(default=None, max_length=200)
    certificate_professor_signer_image_url: str | None = Field(default=None, max_length=500)
    certificate_background_url: str | None = Field(default=None, max_length=500)


class EventRead(EventBase, TimestampMixin):
    id: int
    status: str | None = Field(default=None, pattern="^(pending|approved|denied|finalized)$")
    is_active: bool = True
    creator_id: str | None = None
    creator_name: str | None = None
    creator_email: str | None = None
    cover_image_url: str | None = None


class EventValidated(EventBase):
    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date no puede ser menor que start_date")
        return self
