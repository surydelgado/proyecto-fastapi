from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import base64

from fastapi.templating import Jinja2Templates
from weasyprint import HTML

from app.config import APP_BASE_URL
from app.services.qr_service import generate_qr_png_bytes

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

MONTHS_ES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


@dataclass
class CertificateAssets:
    logo_data_uri: str
    qr_data_uri: str


def _to_utc(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = value
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_date_es(value: str | datetime | None) -> str:
    dt = _to_utc(value)
    if not dt:
        return ""
    return f"{dt.day} de {MONTHS_ES[dt.month - 1]} de {dt.year}"


def format_time_es(value: str | datetime | None) -> str:
    dt = _to_utc(value)
    if not dt:
        return ""
    return dt.strftime("%H:%M")


def build_verify_url(credential_code: str, base_url: str | None = None) -> str:
    base = (base_url or APP_BASE_URL or "").strip().rstrip("/")
    return f"{base}/verify/{credential_code}" if base else f"/verify/{credential_code}"


def build_assets(verify_url: str) -> CertificateAssets:
    logo_path = BASE_DIR / "static" / "images" / "logo-puce.png"
    if logo_path.exists():
        logo_bytes = logo_path.read_bytes()
        logo_data_uri = f"data:image/png;base64,{base64.b64encode(logo_bytes).decode('ascii')}"
    else:
        logo_data_uri = ""

    qr_bytes = generate_qr_png_bytes(verify_url)
    qr_data_uri = f"data:image/png;base64,{base64.b64encode(qr_bytes).decode('ascii')}"
    return CertificateAssets(logo_data_uri=logo_data_uri, qr_data_uri=qr_data_uri)


def render_certificate_html(context: dict, template_name: str = "certificates/default.html") -> str:
    template = templates.get_template(template_name)
    return template.render(**context)


def render_certificate_pdf(html: str) -> bytes:
    from io import BytesIO
    pdf_bytes = HTML(string=html, base_url=str(BASE_DIR)).write_pdf()
    
    # Eliminar páginas en blanco al final usando PyPDF2
    try:
        from PyPDF2 import PdfReader, PdfWriter
        pdf_reader = PdfReader(BytesIO(pdf_bytes))
        
        # Si hay más de 2 páginas, eliminar las páginas en blanco al final
        if len(pdf_reader.pages) > 2:
            pdf_writer = PdfWriter()
            # Agregar solo las primeras 2 páginas
            for i in range(min(2, len(pdf_reader.pages))):
                pdf_writer.add_page(pdf_reader.pages[i])
            
            output_buffer = BytesIO()
            pdf_writer.write(output_buffer)
            return output_buffer.getvalue()
        
        return pdf_bytes
    except ImportError:
        # Si PyPDF2 no está instalado, retornar el PDF original
        return pdf_bytes
    except Exception:
        # Si hay algún error, retornar el PDF original
        return pdf_bytes
