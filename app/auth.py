from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import supabase

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    try:
        token = credentials.credentials
        
        try:
            user_response = supabase.auth.get_user(token)
        except Exception:
            from app.config import SUPABASE_URL, SUPABASE_KEY
            from supabase import create_client
            temp_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            temp_client.auth._headers["Authorization"] = f"Bearer {token}"
            user_response = temp_client.auth.get_user()
        
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido o expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = user_response.user
        
        if not user.email_confirmed_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debes verificar tu correo electrónico antes de acceder. Revisa tu bandeja de entrada."
            )
        
        try:
            user_db_response = supabase.table("users").select("is_active").eq("id", user.id).execute()
            if user_db_response.data and len(user_db_response.data) > 0:
                if not user_db_response.data[0].get("is_active", False):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Tu cuenta ha sido desactivada. Contacta al administrador."
                    )
        except HTTPException:
            raise
        except Exception:
            pass
        
        return {
            "id": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata or {},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Error de autenticación: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[dict]:
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(required_role: str):
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("user_metadata", {}).get("role", "student")
        
        if user_role != required_role and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol: {required_role}",
            )
        
        return user
    
    return role_checker


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    user_role = user.get("user_metadata", {}).get("role", "student")
    
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador",
        )
    
    return user
