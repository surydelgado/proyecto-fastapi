"""
API de gestión de usuarios usando Supabase Auth y Database.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from app.config import supabase
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.auth import get_current_user, require_admin


router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo usuario",
)
async def register_user(payload: UserCreate):
    """
    Registra un nuevo usuario en el sistema.
    Crea el usuario en Supabase Auth y almacena información adicional en la tabla users.
    """
    try:
        # Crear usuario en Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {
                "data": {
                    "full_name": payload.full_name,
                    "role": "student",  # Rol por defecto
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear el usuario"
            )
        
        # Crear registro en la tabla users con información adicional
        user_data = {
            "id": auth_response.user.id,  # Usar el UUID de Auth
            "names": payload.full_name.split()[0] if payload.full_name.split() else payload.full_name,
            "surnames": " ".join(payload.full_name.split()[1:]) if len(payload.full_name.split()) > 1 else "",
            "email": payload.email,
            "cedula": "",  # Se puede actualizar después
            "role": "student",
            "is_active": True,
        }
        
        # Insertar en la tabla users
        db_response = supabase.table("users").insert(user_data).execute()
        
        if not db_response.data or len(db_response.data) == 0:
            # Si falla la inserción en la tabla, el usuario ya existe en Auth
            # Intentar obtener el usuario existente
            db_response = supabase.table("users").select("*").eq("id", auth_response.user.id).execute()
        
        return {
            "id": auth_response.user.id,
            "full_name": payload.full_name,
            "email": payload.email,
            "is_active": True,
            "created_at": auth_response.user.created_at,
        }
        
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El usuario ya está registrado"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar usuario: {error_msg}"
        )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Obtener información del usuario actual",
)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Obtiene la información del usuario autenticado.
    """
    try:
        # Obtener información adicional de la tabla users
        db_response = supabase.table("users").select("*").eq("id", current_user["id"]).execute()
        
        if db_response.data and len(db_response.data) > 0:
            user_data = db_response.data[0]
            full_name = f"{user_data.get('names', '')} {user_data.get('surnames', '')}".strip()
            
            return {
                "id": current_user["id"],
                "full_name": full_name or current_user.get("user_metadata", {}).get("full_name", ""),
                "email": current_user["email"],
                "is_active": user_data.get("is_active", True),
                "created_at": user_data.get("created_at"),
            }
        
        # Si no existe en la tabla users, retornar solo info de Auth
        return {
            "id": current_user["id"],
            "full_name": current_user.get("user_metadata", {}).get("full_name", ""),
            "email": current_user["email"],
            "is_active": True,
            "created_at": None,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener información del usuario: {str(e)}"
        )


@router.get(
    "/",
    response_model=list[UserRead],
    summary="Listar usuarios (solo admin)",
)
async def list_users(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(require_admin)
):
    """
    Lista todos los usuarios del sistema.
    Solo accesible para administradores.
    """
    try:
        response = supabase.table("users").select("*").range(skip, skip + limit - 1).execute()
        
        users = []
        for user_data in (response.data or []):
            full_name = f"{user_data.get('names', '')} {user_data.get('surnames', '')}".strip()
            users.append({
                "id": user_data["id"],
                "full_name": full_name,
                "email": user_data.get("email", ""),
                "is_active": user_data.get("is_active", True),
                "created_at": user_data.get("created_at"),
            })
        
        return users
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar usuarios: {str(e)}"
        )


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Obtener un usuario por ID (solo admin o el mismo usuario)",
)
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene la información de un usuario específico.
    Los usuarios solo pueden ver su propia información, excepto los administradores.
    """
    user_role = current_user.get("user_metadata", {}).get("role", "student")
    
    # Verificar permisos
    if user_id != current_user["id"] and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver este usuario"
        )
    
    try:
        response = supabase.table("users").select("*").eq("id", user_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        user_data = response.data[0]
        full_name = f"{user_data.get('names', '')} {user_data.get('surnames', '')}".strip()
        
        return {
            "id": user_data["id"],
            "full_name": full_name,
            "email": user_data.get("email", ""),
            "is_active": user_data.get("is_active", True),
            "created_at": user_data.get("created_at"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener usuario: {str(e)}"
        )


@router.put(
    "/{user_id}",
    response_model=UserRead,
    summary="Actualizar un usuario",
)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Actualiza la información de un usuario.
    Los usuarios solo pueden actualizar su propia información, excepto los administradores.
    """
    user_role = current_user.get("user_metadata", {}).get("role", "student")
    
    # Verificar permisos
    if user_id != current_user["id"] and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para actualizar este usuario"
        )
    
    try:
        # Preparar datos para actualizar
        update_data = {}
        
        if payload.full_name:
            name_parts = payload.full_name.split()
            update_data["names"] = name_parts[0] if name_parts else payload.full_name
            update_data["surnames"] = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        
        if payload.email:
            update_data["email"] = payload.email
        
        if payload.is_active is not None and user_role == "admin":
            update_data["is_active"] = payload.is_active
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay datos para actualizar"
            )
        
        # Actualizar en la tabla users
        response = supabase.table("users").update(update_data).eq("id", user_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        user_data = response.data[0]
        full_name = f"{user_data.get('names', '')} {user_data.get('surnames', '')}".strip()
        
        # Si se actualizó la contraseña, actualizarla en Auth
        if payload.password:
            supabase.auth.update_user({"password": payload.password})
        
        return {
            "id": user_data["id"],
            "full_name": full_name,
            "email": user_data.get("email", ""),
            "is_active": user_data.get("is_active", True),
            "created_at": user_data.get("created_at"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar usuario: {str(e)}"
        )
