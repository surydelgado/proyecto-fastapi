"""
Servicio para generar y validar tokens QR de eventos.
Los tokens identifican eventos y tienen expiración basada en la fecha de fin del evento.
"""
import hmac
import hashlib
import base64
import time
from typing import Optional
from datetime import datetime, timedelta

from app.config import QR_TOKEN_SECRET

TOKEN_SEP = "."
DEFAULT_EXPIRY_DAYS = 30


def _b64_encode(data: bytes) -> str:
    """Codifica bytes a base64 URL-safe sin padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(s: str) -> Optional[bytes]:
    """Decodifica base64 URL-safe."""
    try:
        pad = 4 - len(s) % 4
        if pad != 4:
            s += "=" * pad
        return base64.urlsafe_b64decode(s)
    except Exception:
        return None


def generate_qr_token(event_id: int, expiry_ts: Optional[int] = None) -> str:
    """
    Genera un token firmado para el QR del evento.
    Formato: event_id:expiry_ts firmado con HMAC-SHA256.
    """
    if expiry_ts is None:
        expiry_ts = int(time.time()) + (DEFAULT_EXPIRY_DAYS * 86400)
    
    payload = f"{event_id}:{expiry_ts}"
    payload_b64 = _b64_encode(payload.encode("utf-8"))
    secret = (QR_TOKEN_SECRET or "").encode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    
    return f"{payload_b64}{TOKEN_SEP}{sig}"


def validate_qr_token(token: str) -> Optional[tuple[int, int]]:
    """
    Valida el token QR y devuelve (event_id, expiry_ts) o None si inválido/expirado.
    """
    if not token or TOKEN_SEP not in token:
        return None
    
    parts = token.split(TOKEN_SEP, 1)
    if len(parts) != 2:
        return None
    
    payload_b64, sig = parts[0], parts[1]
    secret = (QR_TOKEN_SECRET or "").encode("utf-8")
    expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(expected_sig, sig):
        return None
    
    raw = _b64_decode(payload_b64)
    if not raw:
        return None
    
    try:
        decoded = raw.decode("utf-8")
        event_id_s, expiry_s = decoded.split(":", 1)
        event_id = int(event_id_s)
        expiry_ts = int(expiry_s)
    except (ValueError, AttributeError):
        return None
    
    if time.time() > expiry_ts:
        return None
    
    return event_id, expiry_ts
