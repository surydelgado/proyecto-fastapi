from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import Client

from app.auth import get_current_user, get_current_user_optional, require_admin
from app.config import APP_BASE_URL, supabase, supabase_admin
from app.schemas.credential import CredentialIssueSummary, CredentialMineRead
from app.services.certificate_service import (
    build_assets,
    build_verify_url,
    format_date_es,
    format_time_es,
    render_certificate_html,
    render_certificate_pdf,
)
from app.services.email import send_credential_email

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _sb() -> Client:
    return supabase_admin if supabase_admin else supabase


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


def _get_event_or_404(event_id: int) -> dict:
    response = _sb().table("events").select("*").eq("id", event_id).execute()
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado")
    return response.data[0]


def _is_event_finished(event: dict) -> bool:
    status_value = (event.get("status") or "").lower()
    if status_value == "finalized":
        return True
    if status_value != "approved":
        return False
    end_dt = _to_utc(event.get("end_date"))
    if not end_dt:
        return False
    return datetime.now(timezone.utc) >= end_dt


def _get_base_url(request: Request | None = None) -> str:
    base = (APP_BASE_URL or "").strip().rstrip("/")
    if base:
        return base
    if request:
        return str(request.base_url).rstrip("/")
    return ""


def _generate_unique_code() -> str:
    return secrets.token_urlsafe(18).replace("-", "").replace("_", "")


def _build_event_phrase(event: dict) -> str:
    event_type = (event.get("event_type") or "").strip().lower()
    title = event.get("title") or "evento académico"
    if "taller" in event_type:
        return f"el taller académico \"{title}\""
    if "curso" in event_type:
        return f"el curso académico \"{title}\""
    if "conferencia" in event_type:
        return f"la conferencia académica \"{title}\""
    if "capacit" in event_type:
        return f"la capacitación \"{title}\""
    if event_type:
        return f"el evento académico \"{title}\" ({event_type})"
    return f"el evento académico \"{title}\""


def _duration_hours(event: dict) -> int | None:
    start_dt = _to_utc(event.get("start_date"))
    end_dt = _to_utc(event.get("end_date"))
    if not start_dt or not end_dt:
        return None
    if end_dt <= start_dt:
        return None
    hours = (end_dt - start_dt).total_seconds() / 3600
    rounded = int(round(hours))
    return max(1, rounded)


def _validate_event_dates(event: dict) -> None:
    start_dt = _to_utc(event.get("start_date"))
    end_dt = _to_utc(event.get("end_date"))
    if not start_dt or not end_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El evento no tiene fechas válidas para emitir el certificado.",
        )
    if end_dt < start_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de fin del evento es anterior a la fecha de inicio.",
        )


def _is_long_form_event(event_type: str) -> bool:
    event_type = (event_type or "").lower()
    return "curso" in event_type or "program" in event_type


def _build_folio(credential_id: int | None, issued_at: str | datetime | None) -> str:
    year = _to_utc(issued_at).year if issued_at else datetime.now(timezone.utc).year
    numeric = int(credential_id or 0)
    return f"PUCE-{year}-{numeric:06d}"


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return ""
    name, domain = email.split("@", 1)
    if not name:
        return f"*@{domain}"
    return f"{name[0]}***@{domain}"


@router.post(
    "/admin/events/{event_id}/issue-credentials",
    response_model=CredentialIssueSummary,
    status_code=status.HTTP_200_OK,
    summary="Emitir credenciales para asistentes de un evento",
    dependencies=[Depends(require_admin)],
)
async def issue_credentials(event_id: int, request: Request, background: BackgroundTasks):
    event = _get_event_or_404(event_id)
    if not event.get("requires_certificate", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El evento no requiere certificados",
        )
    _validate_event_dates(event)
    if not _is_event_finished(event):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El evento aún no ha finalizado",
        )

    sb = _sb()
    attendance_response = (
        sb.table("attendances")
        .select("user_id, attended_at")
        .eq("event_id", event_id)
        .eq("attended", True)
        .execute()
    )
    attendees = attendance_response.data or []
    total_attendees = len(attendees)
    if total_attendees == 0:
        return {"total_attendees": 0, "issued": 0, "existing": 0, "failed": 0}

    existing_response = sb.table("credentials").select("user_id").eq("event_id", event_id).execute()
    existing_user_ids = {row.get("user_id") for row in (existing_response.data or []) if row.get("user_id")}

    new_user_ids = [row.get("user_id") for row in attendees if row.get("user_id") not in existing_user_ids]
    if not new_user_ids:
        return {
            "total_attendees": total_attendees,
            "issued": 0,
            "existing": len(existing_user_ids),
            "failed": 0,
        }

    users_response = (
        sb.table("users")
        .select("id, names, surnames, cedula, email")
        .in_("id", new_user_ids)
        .execute()
    )
    users_map = {user["id"]: user for user in (users_response.data or [])}

    issued = 0
    failed = 0
    base_url = _get_base_url(request)
    dashboard_url = f"{base_url}/dashboard" if base_url else "/dashboard"
    bucket_name = "certificates"
    template_name = "default"
    template_path = BASE_DIR / "templates" / "certificates" / "default.html"

    for user_id in new_user_ids:
        user = users_map.get(user_id, {})
        if not user:
            failed += 1
            continue

        code = _generate_unique_code()
        for _ in range(5):
            collision_check = sb.table("credentials").select("id").eq("credential_code", code).execute()
            if not collision_check.data:
                break
            code = _generate_unique_code()

        issued_at = datetime.now(timezone.utc)
        verify_url = build_verify_url(code, base_url=base_url)
        assets = build_assets(verify_url)
        event_phrase = _build_event_phrase(event)
        duration_hours = _duration_hours(event)
        if duration_hours is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo calcular la duración del evento.",
            )
        event_type = event.get("event_type") or ""
        is_long_form = _is_long_form_event(event_type)

        signer_name = (event.get("certificate_signer_name") or "").strip()
        signer_role = (event.get("certificate_signer_role") or "").strip()
        second_signer_name = (event.get("certificate_professor_signer_name") or "").strip()
        second_signer_role = (event.get("certificate_professor_signer_role") or "").strip()
        if not signer_name or not signer_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes configurar el nombre y cargo del firmante institucional.",
            )
        if not second_signer_name or not second_signer_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes configurar el nombre y cargo del segundo firmante institucional.",
            )

        context = {
            "certificate_title": event.get("certificate_title") or "Certificado de Asistencia",
            "full_name": f"{user.get('names', '')} {user.get('surnames', '')}".strip() or "Participante",
            "cedula": user.get("cedula") or "",
            "event_title": event.get("title") or "Evento académico",
            "event_phrase": event_phrase,
            "event_type": event_type,
            "issued_date": format_date_es(issued_at),
            "issued_time": format_time_es(issued_at),
            "event_start_date": format_date_es(event.get("start_date")),
            "event_end_date": format_date_es(event.get("end_date")),
            "location": event.get("location") or "",
            "duration_hours": duration_hours,
            "is_long_form": is_long_form,
            "signer_name": signer_name,
            "signer_role": signer_role,
            "signer_image_url": event.get("certificate_signer_image_url") or "",
            "requires_professor_signature": True,
            "professor_signer_name": second_signer_name,
            "professor_signer_role": second_signer_role,
            "professor_signer_image_url": event.get("certificate_professor_signer_image_url") or "",
            "credential_code": code,
            "verify_url": verify_url,
            "logo_data_uri": assets.logo_data_uri,
            "qr_data_uri": assets.qr_data_uri,
            "background_url": event.get("certificate_background_url") or "",
            "university_name": "PUCE Manabí – Eventos Académicos",
        }

        try:
            credential_data = {
                "credential_code": code,
                "user_id": user_id,
                "event_id": event_id,
                "issued_at": issued_at.isoformat(),
                "is_valid": True,
            }
            insert_response = sb.table("credentials").insert(credential_data).execute()
            if not insert_response.data:
                failed += 1
                continue
            credential_row = insert_response.data[0]
            folio = _build_folio(credential_row.get("id"), credential_row.get("issued_at") or issued_at)
            context["folio"] = folio

            html = render_certificate_html(context, template_name=f"certificates/{template_name}.html")
            pdf_bytes = render_certificate_pdf(html)
            file_path = f"event_{event_id}/user_{user_id}/credential_{code}.pdf"
            sb.storage.from_(bucket_name).upload(
                file_path,
                pdf_bytes,
                file_options={"content-type": "application/pdf", "upsert": "true"},
            )
            sb.table("credentials").update({"certificate_url": file_path}).eq("id", credential_row.get("id")).execute()
            sb.table("notifications").insert(
                {
                    "user_id": user_id,
                    "title": "Microcredencial disponible",
                    "message": f"Tu microcredencial de {event.get('title') or 'evento académico'} ya está lista.",
                    "link_url": verify_url,
                    "type": "credential",
                    "is_read": False,
                }
            ).execute()

            user_email = user.get("email") or ""
            if user_email:
                background.add_task(
                    send_credential_email,
                    user_email,
                    context.get("full_name") or "",
                    context.get("event_title") or "",
                    verify_url,
                    dashboard_url,
                )
            issued += 1
        except Exception:
            failed += 1
            continue

    existing_count = len(existing_user_ids)
    return {
        "total_attendees": total_attendees,
        "issued": issued,
        "existing": existing_count,
        "failed": failed,
    }


@router.post(
    "/credentials/admin/events/{event_id}/issue",
    response_model=CredentialIssueSummary,
    status_code=status.HTTP_200_OK,
    summary="Emitir credenciales por evento (alias)",
    dependencies=[Depends(require_admin)],
)
async def issue_credentials_alias(event_id: int, request: Request, background: BackgroundTasks):
    return await issue_credentials(event_id, request, background)


@router.post(
    "/admin/credentials/{credential_code}/revoke",
    summary="Revocar una credencial",
    dependencies=[Depends(require_admin)],
)
async def revoke_credential(credential_code: str):
    sb = _sb()
    response = sb.table("credentials").select("*").eq("credential_code", credential_code).execute()
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial no encontrada")
    sb.table("credentials").update({"is_valid": False}).eq("credential_code", credential_code).execute()
    return {"status": "revoked", "credential_code": credential_code}


@router.get(
    "/verify/{credential_code}",
    response_class=HTMLResponse,
    summary="Verificar credencial pública",
)
async def verify_credential(
    request: Request,
    credential_code: str,
    current_user: dict | None = Depends(get_current_user_optional),
):
    sb = _sb()
    credential_response = (
        sb.table("credentials")
        .select("id, credential_code, user_id, event_id, issued_at, is_valid, certificate_url")
        .eq("credential_code", credential_code)
        .execute()
    )
    if not credential_response.data:
        return templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "is_valid": False,
                "not_found": True,
                "credential_code": credential_code,
                "folio": "",
                "issued_date": "",
                "issued_time": "",
                "full_name": "",
                "cedula": "",
                "email": "",
                "event_title": "",
                "event_phrase": "",
                "event_location": "",
                "event_start_date": "",
                "event_end_date": "",
                "event_type": "",
                "duration_hours": None,
                "verify_url": build_verify_url(credential_code, base_url=_get_base_url(request)),
                "university_name": "PUCE Manabí – Eventos Académicos",
                "is_authenticated": current_user is not None,
                "can_download": False,
                "download_url": "",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    credential = credential_response.data[0]
    user = {}
    event = {}

    if credential.get("user_id"):
        user_response = (
            sb.table("users")
            .select("id, names, surnames, cedula, email")
            .eq("id", credential["user_id"])
            .execute()
        )
        if user_response.data:
            user = user_response.data[0]

    if credential.get("event_id"):
        event_response = (
            sb.table("events")
            .select(
                "id, title, location, start_date, end_date, event_type, requires_certificate"
            )
            .eq("id", credential["event_id"])
            .execute()
        )
        if event_response.data:
            event = event_response.data[0]

    full_name = f"{user.get('names', '')} {user.get('surnames', '')}".strip()
    verify_url = build_verify_url(credential_code, base_url=_get_base_url(request))
    is_valid = bool(credential.get("is_valid", False))
    event_phrase = _build_event_phrase(event)
    duration_hours = _duration_hours(event)
    folio = _build_folio(credential.get("id"), credential.get("issued_at"))
    user_email = user.get("email") or ""
    masked_email = _mask_email(user_email)
    is_authenticated = current_user is not None
    is_admin = (current_user or {}).get("role") == "admin"
    is_owner = (current_user or {}).get("id") == credential.get("user_id")
    can_download = is_authenticated and (is_admin or is_owner) and is_valid

    return templates.TemplateResponse(
        "verify.html",
        {
            "request": request,
            "is_valid": is_valid,
            "not_found": False,
            "credential_code": credential_code,
            "folio": folio,
            "issued_date": format_date_es(credential.get("issued_at")),
            "issued_time": format_time_es(credential.get("issued_at")),
            "full_name": full_name,
            "cedula": user.get("cedula") or "",
            "email": masked_email,
            "event_title": event.get("title") or "",
            "event_phrase": event_phrase,
            "event_location": event.get("location") or "",
            "event_start_date": format_date_es(event.get("start_date")),
            "event_end_date": format_date_es(event.get("end_date")),
            "event_type": event.get("event_type") or "",
            "duration_hours": duration_hours,
            "verify_url": verify_url,
            "university_name": "PUCE Manabí – Eventos Académicos",
            "is_authenticated": is_authenticated,
            "can_download": can_download,
            "download_url": f"/credentials/{credential_code}/download",
            "is_valid_for_download": is_valid,
        },
    )


@router.get(
    "/credentials/mine",
    response_model=list[CredentialMineRead],
    summary="Listar mis credenciales",
)
async def list_my_credentials(current_user: dict = Depends(get_current_user)):
    sb = _sb()
    user_id = current_user["id"]
    response = (
        sb.table("credentials")
        .select("credential_code, event_id, issued_at, is_valid, id")
        .eq("user_id", user_id)
        .order("issued_at", desc=True)
        .execute()
    )
    rows = response.data or []
    event_ids = [row.get("event_id") for row in rows if row.get("event_id") is not None]
    events_map = {}
    if event_ids:
        events_response = (
            sb.table("events")
            .select("id, title")
            .in_("id", event_ids)
            .execute()
        )
        for event in (events_response.data or []):
            events_map[event["id"]] = event

    base_url = _get_base_url()
    data = []
    for row in rows:
        event = events_map.get(row.get("event_id"), {})
        code = row.get("credential_code")
        folio = _build_folio(row.get("id"), row.get("issued_at"))
        data.append(
            {
                "event_id": row.get("event_id"),
                "event_title": event.get("title") if event else None,
                "issued_at": row.get("issued_at"),
                "status": "valid" if row.get("is_valid", False) else "revoked",
                "verify_url": build_verify_url(code, base_url=base_url) if code else None,
                "credential_code": code,
                "folio": folio,
            }
        )

    return data


@router.get(
    "/credentials/{credential_code}/download",
    summary="Descargar PDF de una credencial",
)
async def download_credential(
    credential_code: str,
    current_user: dict = Depends(get_current_user),
):
    sb = _sb()
    credential_response = (
        sb.table("credentials")
        .select("id, credential_code, user_id, is_valid, certificate_url")
        .eq("credential_code", credential_code)
        .execute()
    )
    if not credential_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial no encontrada")
    credential = credential_response.data[0]

    if not credential.get("is_valid", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La credencial ha sido revocada",
        )

    user_role = current_user.get("role") or current_user.get("user_metadata", {}).get("role", "student")
    is_admin = user_role == "admin"
    is_owner = str(credential.get("user_id")) == str(current_user.get("id"))
    if not (is_admin or is_owner):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para descargar")

    storage_path = credential.get("certificate_url") or ""
    if not storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no disponible")

    bucket_name = "certificates"
    signed = sb.storage.from_(bucket_name).create_signed_url(storage_path, 60)
    signed_url = None
    if isinstance(signed, dict):
        signed_url = (
            signed.get("signedURL")
            or signed.get("signedUrl")
            or signed.get("signed_url")
            or (signed.get("data") or {}).get("signedURL")
            or (signed.get("data") or {}).get("signedUrl")
            or (signed.get("data") or {}).get("signed_url")
        )
    if not signed_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo generar URL firmada")

    return RedirectResponse(url=signed_url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/credentials/{credential_code}/access",
    summary="Consultar permisos para descargar una credencial",
)
async def credential_access(
    credential_code: str,
    current_user: dict | None = Depends(get_current_user_optional),
):
    sb = _sb()
    credential_response = (
        sb.table("credentials")
        .select("id, credential_code, user_id, is_valid, certificate_url")
        .eq("credential_code", credential_code)
        .execute()
    )
    if not credential_response.data:
        return {
            "is_authenticated": current_user is not None,
            "can_download": False,
            "reason": "not_found",
        }
    credential = credential_response.data[0]

    is_valid = bool(credential.get("is_valid", False))
    if not is_valid:
        return {
            "is_authenticated": current_user is not None,
            "can_download": False,
            "reason": "revoked",
        }

    if not current_user:
        return {
            "is_authenticated": False,
            "can_download": False,
            "reason": "login_required",
        }

    user_role = current_user.get("role") or current_user.get("user_metadata", {}).get("role", "student")
    is_admin = user_role == "admin"
    is_owner = str(credential.get("user_id")) == str(current_user.get("id"))
    can_download = is_admin or is_owner
    return {
        "is_authenticated": True,
        "can_download": can_download,
        "reason": "ok" if can_download else "not_authorized",
        "download_url": f"/credentials/{credential_code}/download",
    }
