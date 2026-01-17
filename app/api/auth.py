"""
API de autenticación usando Supabase Auth.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from app.config import supabase
from app.schemas.user import UserRegister


router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class RegisterResponse(BaseModel):
    message: str
    user_id: str | None = None


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Iniciar sesión",
)
async def login(payload: LoginRequest):
    """
    Inicia sesión con email y contraseña.
    Retorna un token JWT de Supabase.
    
    Requisitos:
    - El email debe estar verificado
    - El usuario debe estar activo (is_active = true)
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
        
        if not response.session or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas"
            )
        
        # Verificar que el email esté confirmado
        if not response.user.email_confirmed_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debes verificar tu correo electrónico antes de iniciar sesión. Revisa tu bandeja de entrada."
            )
        
        # Obtener información del usuario desde la tabla users (incluyendo el rol)
        user_response = supabase.table("users").select("is_active, role, names, surnames").eq("id", response.user.id).execute()
        
        user_role = "externo"  # Rol por defecto
        user_names = ""
        user_surnames = ""
        
        if user_response.data and len(user_response.data) > 0:
            user_data = user_response.data[0]
            
            # Verificar que el usuario esté activo
            if not user_data.get("is_active", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tu cuenta ha sido desactivada. Contacta al administrador."
                )
            
            # Obtener el rol desde la tabla users
            user_role = user_data.get("role", "externo")
            user_names = user_data.get("names", "")
            user_surnames = user_data.get("surnames", "")
        else:
            # Si no existe en la tabla users, crear el registro básico
            # Esto puede pasar si el usuario fue creado directamente en Supabase Auth
            default_role = response.user.user_metadata.get("role", "externo")
            supabase.table("users").insert({
                "id": response.user.id,
                "names": response.user.user_metadata.get("names", ""),
                "surnames": response.user.user_metadata.get("surnames", ""),
                "email": response.user.email,
                "cedula": response.user.user_metadata.get("cedula", ""),
                "role": default_role,
                "is_active": True,
            }).execute()
            user_role = default_role
        
        return {
            "access_token": response.session.access_token,
            "token_type": "bearer",
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "role": user_role,
                "names": user_names,
                "surnames": user_surnames,
                "user_metadata": response.user.user_metadata or {},
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "invalid" in error_msg or "credentials" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas"
            )
        if "verify" in error_msg or "confirm" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debes verificar tu correo electrónico antes de iniciar sesión."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al iniciar sesión: {str(e)}"
        )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo usuario",
)
async def register(payload: UserRegister):
    """
    Registra un nuevo usuario con nombres, apellidos, cédula, email y contraseña.
    
    Asigna el rol automáticamente:
    - "interno" si el email termina en @pucesm.edu.ec
    - "externo" en caso contrario
    
    Requiere verificación de correo antes de permitir el acceso.
    """
    try:
        # Determinar el rol según el dominio del email
        role = "interno" if payload.email.endswith("@pucesm.edu.ec") else "externo"
        
        # Crear usuario en Supabase Auth con verificación de email requerida
        response = supabase.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {
                "data": {
                    "names": payload.names,
                    "surnames": payload.surnames,
                    "cedula": payload.cedula,
                    "role": role,
                },
                "email_redirect_to": None  # Se puede configurar una URL de redirección
            }
        })
        
        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al registrar el usuario"
            )
        
        # Crear registro en la tabla users con información adicional
        user_data = {
            "id": response.user.id,  # Usar el UUID de Auth
            "names": payload.names,
            "surnames": payload.surnames,
            "cedula": payload.cedula,
            "email": payload.email,
            "role": role,
            "is_active": True,  # Activo por defecto, pero requiere verificación de email
        }
        
        # Insertar en la tabla users
        try:
            db_response = supabase.table("users").insert(user_data).execute()
        except Exception as db_error:
            # Si falla la inserción, el usuario ya podría existir
            # Intentar obtener el usuario existente
            db_response = supabase.table("users").select("*").eq("id", response.user.id).execute()
            if not db_response.data or len(db_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error al guardar datos del usuario: {str(db_error)}"
                )
        
        # No retornar token porque el usuario debe verificar su email primero
        return {
            "message": "Usuario registrado exitosamente. Por favor verifica tu correo electrónico antes de iniciar sesión. Revisa tu bandeja de entrada (y la carpeta de spam).",
            "user_id": response.user.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "already" in error_msg or "exists" in error_msg or "duplicate" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está registrado en el sistema"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar usuario: {str(e)}"
        )


@router.post(
    "/logout",
    summary="Cerrar sesión",
)
async def logout():
    """
    Cierra la sesión del usuario actual.
    """
    try:
        supabase.auth.sign_out()
        return {"message": "Sesión cerrada exitosamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al cerrar sesión: {str(e)}"
        )
