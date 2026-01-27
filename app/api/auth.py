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
        
        if not response.user.email_confirmed_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debes verificar tu correo electrónico antes de iniciar sesión. Revisa tu bandeja de entrada."
            )
        
        user_response = supabase.table("users").select("is_active, role, names, surnames").eq("id", response.user.id).execute()
        
        user_role = "externo"
        user_names = ""
        user_surnames = ""
        
        if user_response.data and len(user_response.data) > 0:
            user_data = user_response.data[0]
            
            if not user_data.get("is_active", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tu cuenta ha sido desactivada. Contacta al administrador."
                )
            
            user_role = user_data.get("role", "externo")
            user_names = user_data.get("names", "")
            user_surnames = user_data.get("surnames", "")
        else:
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
    try:
        role = "interno" if payload.email.endswith("@pucesm.edu.ec") else "externo"
        
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
                "email_redirect_to": None
            }
        })
        
        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al registrar el usuario"
            )
        
        user_data = {
            "id": response.user.id,
            "names": payload.names,
            "surnames": payload.surnames,
            "cedula": payload.cedula,
            "email": payload.email,
            "role": role,
            "is_active": True,
        }
        
        import time
        import traceback
        
        try:
            from app.config import supabase_admin, SUPABASE_SERVICE_KEY
            
            time.sleep(0.5)
            
            read_client = supabase_admin if (supabase_admin and SUPABASE_SERVICE_KEY) else supabase
            
            db_response = None
            user_record = None
            
            try:
                db_response = read_client.table("users").select("*").eq("id", response.user.id).execute()
                if db_response.data and len(db_response.data) > 0:
                    user_record = db_response.data[0]
            except Exception as read_error:
                time.sleep(0.5)
                try:
                    db_response = read_client.table("users").select("*").eq("id", response.user.id).execute()
                    if db_response.data and len(db_response.data) > 0:
                        user_record = db_response.data[0]
                except Exception:
                    if not supabase_admin or not SUPABASE_SERVICE_KEY:
                        pass
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Error: No se pudo verificar el registro creado por el trigger. El usuario fue creado en Auth pero puede haber un problema con la tabla users."
                        )
            
            if user_record:
                update_data = {}
                
                if user_record.get("names", "") != payload.names:
                    update_data["names"] = payload.names
                if user_record.get("surnames", "") != payload.surnames:
                    update_data["surnames"] = payload.surnames
                if user_record.get("cedula", "") != payload.cedula:
                    update_data["cedula"] = payload.cedula
                if user_record.get("role", "") != role:
                    update_data["role"] = role
                
                if update_data and supabase_admin and SUPABASE_SERVICE_KEY:
                    try:
                        supabase_admin.table("users").update(update_data).eq("id", response.user.id).execute()
                    except Exception as update_error:
                        print(f"Advertencia: No se pudieron actualizar algunos datos: {str(update_error)}")
            else:
                if supabase_admin and SUPABASE_SERVICE_KEY:
                    try:
                        db_response = supabase_admin.table("users").insert(user_data).execute()
                        user_record = db_response.data[0] if db_response.data else None
                    except Exception as insert_error:
                        error_str = str(insert_error).lower()
                        if ("duplicate" in error_str or "already exists" in error_str or 
                            "unique" in error_str or "foreign key" in error_str or 
                            "23503" in error_str or "23514" in error_str or "constraint" in error_str):
                            time.sleep(0.3)
                            try:
                                db_response = supabase_admin.table("users").select("*").eq("id", response.user.id).execute()
                                if db_response.data and len(db_response.data) > 0:
                                    user_record = db_response.data[0]
                            except Exception:
                                pass
                        else:
                            print(f"Advertencia al insertar usuario (el trigger debería haberlo creado): {str(insert_error)}")
                            pass
                    
        except HTTPException:
            raise
        except Exception as db_error:
            print(f"Error completo en registro: {traceback.format_exc()}")
            pass
        
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


@router.post("/logout", summary="Cerrar sesión")
async def logout():
    try:
        supabase.auth.sign_out()
        return {"message": "Sesión cerrada exitosamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al cerrar sesión: {str(e)}"
        )
