from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    LOCAL_TZ = ZoneInfo("America/Guayaquil")
except ZoneInfoNotFoundError:
    # Fallback for Windows if tzdata is missing.
    LOCAL_TZ = timezone(timedelta(hours=-5))


def _to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def build_ics(event_id: int, title: str, start_dt: datetime, end_dt: datetime, description: str = "") -> str:
    start_local = _to_local(start_dt)
    end_local = _to_local(end_dt)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tzid = "America/Guayaquil"
    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PUCE Manabí//Eventos//ES
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:{tzid}
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0500
TZNAME:ECT
DTSTART:19700101T000000
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:{event_id}@puce-manabi
DTSTAMP:{stamp}
DTSTART;TZID={tzid}:{start_local.strftime('%Y%m%dT%H%M%S')}
DTEND;TZID={tzid}:{end_local.strftime('%Y%m%dT%H%M%S')}
SUMMARY:{title}
DESCRIPTION:{description}
END:VEVENT
END:VCALENDAR
"""
