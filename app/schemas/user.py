from pydantic import EmailStr, Field
from .base import APIModel, TimestampMixin


class UserBase(APIModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr


class UserCreate(UserBase):
    """Schema para crear un nuevo usuario con todos los campos requeridos."""
    password: str = Field(min_length=8, max_length=128)


class UserRegister(APIModel):
    """Schema para registro completo con nombres, apellidos y cédula."""
    names: str = Field(min_length=2, max_length=100, description="Nombres del usuario")
    surnames: str = Field(min_length=2, max_length=100, description="Apellidos del usuario")
    cedula: str = Field(min_length=10, max_length=20, description="Cédula de identidad")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(APIModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=120)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class UserRead(UserBase, TimestampMixin):
    id: int
    is_active: bool



