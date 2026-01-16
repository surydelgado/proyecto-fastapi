from pydantic import EmailStr, Field
from .base import APIModel, TimestampMixin



class UserBase(APIModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(APIModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=120)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class UserRead(UserBase, TimestampMixin):
    id: int
    is_active: bool



