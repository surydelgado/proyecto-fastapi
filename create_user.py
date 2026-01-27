"""
Script para crear usuarios en el sistema con cualquier rol.
Útil para setup inicial, testing y desarrollo.

Uso:
    python create_user.py --role admin --email admin@pucesm.edu.ec --password Admin123!
    python create_user.py --role teacher --email profesor@pucesm.edu.ec --password Profesor123!
    python create_user.py --role interno --email estudiante@pucesm.edu.ec --password Estudiante123!
"""
import os
import sys
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Configurar encoding para Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Cargar variables de entorno
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar configuradas en el archivo .env")
    sys.exit(1)

# Crear cliente admin
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

VALID_ROLES = ["admin", "teacher", "interno", "externo"]

def create_user(role, email, password, names=None, surnames=None, cedula=None):
    """Crea un usuario con el rol especificado"""
    
    if role not in VALID_ROLES:
        print(f"ERROR: Rol inválido. Roles válidos: {', '.join(VALID_ROLES)}")
        return False
    
    # Valores por defecto según el rol
    if not names:
        names = "Admin" if role == "admin" else "Profesor" if role == "teacher" else "Usuario"
    if not surnames:
        surnames = "Sistema" if role == "admin" else "Prueba" if role == "teacher" else "Test"
    if not cedula:
        cedula = "0000000000" if role == "admin" else "1234567890"
    
    if not email or "@" not in email:
        print("ERROR: Email inválido")
        return False
    
    if not password or len(password) < 8:
        print("ERROR: La contraseña debe tener al menos 8 caracteres")
        return False
    
    print(f"\n{'='*50}")
    print(f"CREACIÓN DE USUARIO - Rol: {role.upper()}")
    print("="*50)
    print(f"Email: {email}")
    print(f"Nombre: {names} {surnames}")
    print(f"Cédula: {cedula}")
    print("="*50 + "\n")
    
    try:
        # Crear usuario en Supabase Auth usando el cliente admin
        auth_response = supabase_admin.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "names": names,
                "surnames": surnames,
                "cedula": cedula,
                "role": role
            }
        })
        
        if not auth_response.user:
            print("ERROR: No se pudo crear el usuario en Auth")
            return False
        
        user_id = auth_response.user.id
        print(f"✓ Usuario creado en Auth con ID: {user_id}")
        
        # Esperar un momento para que el trigger procese
        time.sleep(1)
        
        # Verificar si el usuario ya existe en la tabla users (por el trigger)
        try:
            existing_user = supabase_admin.table("users").select("*").eq("id", user_id).execute()
            
            if existing_user.data and len(existing_user.data) > 0:
                # Actualizar el usuario existente con los datos correctos
                print("Actualizando datos del usuario en la base de datos...")
                supabase_admin.table("users").update({
                    "names": names,
                    "surnames": surnames,
                    "cedula": cedula,
                    "email": email,
                    "role": role,
                    "is_active": True
                }).eq("id", user_id).execute()
                print("✓ Usuario actualizado en la base de datos")
            else:
                # Crear el usuario manualmente si el trigger no funcionó
                print("Creando registro en la tabla users...")
                supabase_admin.table("users").insert({
                    "id": user_id,
                    "names": names,
                    "surnames": surnames,
                    "cedula": cedula,
                    "email": email,
                    "role": role,
                    "is_active": True
                }).execute()
                print("✓ Usuario creado en la base de datos")
        except Exception as db_error:
            print(f"ADVERTENCIA al actualizar la tabla users: {str(db_error)}")
            print("   El usuario fue creado en Auth, pero puede necesitar actualización manual")
        
        print("\n" + "="*50)
        print("USUARIO CREADO EXITOSAMENTE")
        print("="*50)
        print(f"\nEmail: {email}")
        print(f"Contraseña: {password}")
        print(f"Nombre: {names} {surnames}")
        print(f"Cédula: {cedula}")
        print(f"Rol: {role}")
        print(f"\nPuedes iniciar sesión ahora con estas credenciales.")
        print("="*50 + "\n")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"\nERROR al crear el usuario: {error_msg}")
        
        if "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            print("\nEl usuario ya existe. Puedes intentar actualizar su rol manualmente.")
        else:
            print("\nVerifica que:")
            print("   1. SUPABASE_SERVICE_KEY esté correctamente configurada")
            print("   2. El email no esté ya registrado")
            print("   3. La contraseña tenga al menos 8 caracteres")
        
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Crear usuario en el sistema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Ejemplos:
  python create_user.py --role admin --email admin@pucesm.edu.ec --password Admin123!
  python create_user.py --role teacher --email profesor@pucesm.edu.ec --password Profesor123!
  python create_user.py --role interno --email estudiante@pucesm.edu.ec --password Estudiante123!
  
Roles válidos: {', '.join(VALID_ROLES)}
        """
    )
    
    parser.add_argument('--role', type=str, required=True, 
                       choices=VALID_ROLES,
                       help=f'Rol del usuario ({", ".join(VALID_ROLES)})')
    parser.add_argument('--email', type=str, required=True, help='Email del usuario')
    parser.add_argument('--password', type=str, required=True, 
                       help='Contraseña (mínimo 8 caracteres)')
    parser.add_argument('--names', type=str, help='Nombres (opcional)')
    parser.add_argument('--surnames', type=str, help='Apellidos (opcional)')
    parser.add_argument('--cedula', type=str, help='Cédula (opcional)')
    
    args = parser.parse_args()
    
    try:
        success = create_user(
            role=args.role,
            email=args.email.lower().strip(),
            password=args.password,
            names=args.names,
            surnames=args.surnames,
            cedula=args.cedula
        )
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nOperación cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR inesperado: {str(e)}")
        sys.exit(1)
