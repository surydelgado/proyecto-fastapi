from datetime import datetime
from pydantic import Field, model_validator
from .base import APIModel, TimestampMixin


class EventBase(APIModel):
    title: str = Field(min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    event_type: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    start_date: datetime
    end_date: datetime
    capacity: int | None = Field(default=None, ge=1)


class EventCreate(EventBase):
    pass


class EventUpdate(APIModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=200)
    start_date: datetime | None = None
    end_date: datetime | None = None
    capacity: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, pattern="^(pending|approved|denied|finalized)$")


class EventRead(EventBase, TimestampMixin):
    id: int
    is_active: bool = True


class EventValidated(EventBase):
    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date no puede ser menor que start_date")
        return self
