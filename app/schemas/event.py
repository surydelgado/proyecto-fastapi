from datetime import datetime
from pydantic import Field, model_validator
from .base import APIModel, TimestampMixin




class EventBase(APIModel):
    title: str = Field(min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=200)
    starts_at: datetime
    ends_at: datetime
    capacity: int | None = Field(default=None, ge=1)


class EventCreate(EventBase):
    pass


class EventUpdate(APIModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=200)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    capacity: int | None = Field(default=None, ge=1)


class EventRead(EventBase, TimestampMixin):
    id: int
    is_active: bool = True


class EventValidated(EventBase):
    @model_validator(mode="after")
    def validate_dates(self):
        if self.ends_at < self.starts_at:
            raise ValueError("ends_at no puede ser menor que starts_at")
        return self

