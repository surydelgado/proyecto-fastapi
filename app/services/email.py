import os
import base64
import resend


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Eventos <onboarding@resend.dev>")


def send_event_email(to_email: str, subject: str, html: str, ics_content: str) -> dict | None:
    if not RESEND_API_KEY:
        return None
    resend.api_key = RESEND_API_KEY
    ics_base64 = base64.b64encode(ics_content.encode("utf-8")).decode("utf-8")
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
