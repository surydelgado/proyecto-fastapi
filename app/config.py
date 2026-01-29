import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
APP_BASE_URL = (os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
QR_TOKEN_SECRET = os.getenv("QR_TOKEN_SECRET") or SUPABASE_SERVICE_KEY or "qr-secret-change-in-production"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "SUPABASE_URL y SUPABASE_KEY deben estar configuradas en el archivo .env"
    )

__all__ = ["SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "supabase", "supabase_admin", "APP_BASE_URL", "QR_TOKEN_SECRET"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

supabase_admin: Client | None = None
if SUPABASE_SERVICE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
