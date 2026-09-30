"""RFC 5545 standard iCalendar (.ics) generator and universal 1-tap web calendar link builder.
Free, zero-billing, zero-OAuth alternative to Google Calendar API.
Compatible with Google Calendar, Apple Calendar, Microsoft Outlook, Thunderbird, iOS, and Android.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus


def escape_ics_text(text: str | None) -> str:
    """Escapes special characters according to RFC 5545 §3.3.11."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", r"\;")
    text = text.replace(",", r"\,")
    text = text.replace("\r\n", r"\n").replace("\n", r"\n").replace("\r", r"\n")
    return text


def format_ics_datetime(dt: datetime) -> str:
    """Formats a datetime in RFC 5545 UTC timestamp format: YYYYMMDDTHHMMSSZ."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def generate_ics_content(
    *,
    appointment_id: str | uuid.UUID,
    summary: str,
    description: str = "",
    start_time: datetime,
    duration_minutes: int = 30,
    location: str = "",
    organizer_name: str = "JKR AI Calling",
    organizer_email: str = "appointments@jkr.ai",
) -> str:
    """Generates an RFC 5545 compliant .ics calendar invite string."""
    now_utc = datetime.now(UTC)
    dtstamp = format_ics_datetime(now_utc)
    dtstart = format_ics_datetime(start_time)
    end_time = start_time + timedelta(minutes=duration_minutes)
    dtend = format_ics_datetime(end_time)

    uid = f"apt-{appointment_id}@jkr.ai"
    clean_summary = escape_ics_text(summary or "Consultation Appointment")
    clean_description = escape_ics_text(description or "Automated Booking via JKR Calling AI Agent")
    clean_location = escape_ics_text(location or "")
    clean_org_name = escape_ics_text(organizer_name)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//JKR Calling//AI Voice Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{clean_summary}",
        f"DESCRIPTION:{clean_description}",
    ]

    if clean_location:
        lines.append(f"LOCATION:{clean_location}")

    lines.extend([
        f"ORGANIZER;CN={clean_org_name}:mailto:{organizer_email}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "SEQUENCE:0",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Appointment Reminder",
        "TRIGGER:-PT30M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    return "\r\n".join(lines) + "\r\n"


def generate_google_calendar_url(
    *,
    summary: str,
    description: str = "",
    start_time: datetime,
    duration_minutes: int = 30,
    location: str = "",
) -> str:
    """Generates a 1-tap Google Calendar web template link (100% free, zero OAuth, zero billing)."""
    dtstart = format_ics_datetime(start_time)
    end_time = start_time + timedelta(minutes=duration_minutes)
    dtend = format_ics_datetime(end_time)

    params = (
        f"action=TEMPLATE"
        f"&text={quote_plus(summary or 'Consultation Appointment')}"
        f"&dates={dtstart}/{dtend}"
        f"&details={quote_plus(description or '')}"
        f"&location={quote_plus(location or '')}"
    )
    return f"https://calendar.google.com/calendar/render?{params}"


def generate_outlook_calendar_url(
    *,
    summary: str,
    description: str = "",
    start_time: datetime,
    duration_minutes: int = 30,
    location: str = "",
) -> str:
    """Generates a 1-tap Microsoft Outlook / Office 365 web calendar link."""
    dtstart = format_ics_datetime(start_time)
    end_time = start_time + timedelta(minutes=duration_minutes)
    dtend = format_ics_datetime(end_time)

    params = (
        f"path=/calendar/action/compose"
        f"&rru=addevent"
        f"&subject={quote_plus(summary or 'Consultation Appointment')}"
        f"&startdt={dtstart}"
        f"&enddt={dtend}"
        f"&body={quote_plus(description or '')}"
        f"&location={quote_plus(location or '')}"
    )
    return f"https://outlook.live.com/calendar/0/deeplink/compose?{params}"


def get_appointment_calendar_links(
    *,
    appointment_id: str | uuid.UUID,
    summary: str,
    description: str = "",
    start_time: datetime,
    duration_minutes: int = 30,
    location: str = "",
    api_base_url: str | None = None,
) -> dict[str, str]:
    """Returns a full dictionary of calendar links for an appointment."""
    base_url = api_base_url or os.getenv("NEXT_PUBLIC_API_URL") or "https://jkr-api.onrender.com"
    base_url = base_url.rstrip("/")
    ics_url = f"{base_url}/api/v1/appointments/{appointment_id}/invite.ics"

    return {
        "ics_download_url": ics_url,
        "google_calendar_url": generate_google_calendar_url(
            summary=summary,
            description=description,
            start_time=start_time,
            duration_minutes=duration_minutes,
            location=location,
        ),
        "outlook_calendar_url": generate_outlook_calendar_url(
            summary=summary,
            description=description,
            start_time=start_time,
            duration_minutes=duration_minutes,
            location=location,
        ),
    }
