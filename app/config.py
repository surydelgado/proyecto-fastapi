"""
Configuración del proyecto y cliente de Supabase.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar variables de entorno
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Configuración de Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # Para operaciones admin

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "SUPABASE_URL y SUPABASE_KEY deben estar configuradas en el archivo .env"
    )

# Exportar variables para uso en otros módulos
__all__ = ["SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "supabase", "supabase_admin"]

# Cliente de Supabase para operaciones del usuario
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Cliente de Supabase para operaciones administrativas (si se necesita)
supabase_admin: Client | None = None
if SUPABASE_SERVICE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
