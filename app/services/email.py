import os
import base64
import logging
import resend


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Eventos <onboarding@resend.dev>")
logger = logging.getLogger(__name__)


def send_event_email(to_email: str, subject: str, html: str, ics_content: str) -> dict | None:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY no configurada; se omite el envio de correos.")
        return None
    if not to_email:
        logger.warning("Email destino vacio; se omite el envio de correos.")
        return None

    resend.api_key = RESEND_API_KEY
    ics_base64 = base64.b64encode(ics_content.encode("utf-8")).decode("utf-8")
    try:
        return resend.Emails.send(
            {
                "from": RESEND_FROM,
                "to": to_email,
                "subject": subject,
                "html": html,
                "attachments": [
                    {
                        "filename": "evento.ics",
                        "content": ics_base64,
                    }
                ],
            }
        )
    except Exception:
        logger.exception("Fallo al enviar correo con Resend.")
        return None


def send_credential_email(
    to_email: str,
    full_name: str,
    event_title: str,
    verify_url: str,
    download_url: str | None = None,
) -> dict | None:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY no configurada; se omite el envio de correos.")
        return None
    if not to_email:
        logger.warning("Email destino vacio; se omite el envio de correos.")
        return None

    resend.api_key = RESEND_API_KEY
    safe_name = full_name or "participante"
    safe_event = event_title or "evento académico"
    download_block = ""
    if download_url:
        download_block = (
            f'<p style="margin:12px 0 0;">'
            f'Puedes descargarla iniciando sesión aquí: '
            f'<a href="{download_url}" style="color:#0c3c78;">Descargar microcredencial</a>.'
            f"</p>"
        )

    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;background-color:#f4f6fb;padding:24px;">
        <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e3e7f0;">
            <div style="background:#0c3c78;color:#ffffff;padding:20px 24px;">
                <div style="font-size:14px;letter-spacing:0.5px;text-transform:uppercase;">PUCE Manabí · Eventos Académicos</div>
                <h1 style="margin:6px 0 0;font-size:22px;">Tu microcredencial está lista</h1>
            </div>
            <div style="padding:22px 24px;color:#1f2a44;">
                <p style="margin:0 0 12px;">Hola {safe_name},</p>
                <p style="margin:0 0 12px;">Tu microcredencial para <strong>{safe_event}</strong> ya está disponible.</p>
                <p style="margin:0 0 12px;">
                    Verifica la credencial aquí:
                    <a href="{verify_url}" style="color:#0c3c78;">{verify_url}</a>
                </p>
                {download_block}
            </div>
            <div style="padding:14px 24px;background:#f2f5fb;color:#2a3d66;font-size:12px;">
                Si tienes dudas, responde a este correo.
            </div>
        </div>
    </div>
    """

    try:
        return resend.Emails.send(
            {
                "from": RESEND_FROM,
                "to": to_email,
                "subject": f"Microcredencial disponible: {safe_event}",
                "html": html,
            }
        )
    except Exception:
        logger.exception("Fallo al enviar correo de microcredencial con Resend.")
        return None
