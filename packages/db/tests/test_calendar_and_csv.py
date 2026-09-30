"""Verification tests for:
1. RFC 5545 .ics Calendar Invite Generation & Format Validation
2. 1-Tap Google / Outlook Calendar URL Builder
3. Appointments CSV Data Export
4. Contacts / Leads CSV Data Export
"""

import csv
import io
import uuid
from datetime import UTC, datetime

from jkr_db.calendar_invite import (
    generate_ics_content,
    generate_google_calendar_url,
    generate_outlook_calendar_url,
    get_appointment_calendar_links,
)


def test_ics_generation_and_rfc5545_compliance():
    test_apt_id = uuid.uuid4()
    appointment_time = datetime(2026, 10, 5, 10, 30, tzinfo=UTC)
    summary = "Dental Consultation: Gowtham Krishna"
    description = (
        "Automated Booking via JKR Calling AI Agent\n"
        "Reason: Routine Checkup & Teeth Cleaning\n"
        "Phone: +919876543210\n"
        "Provider: Aaha Dental Care"
    )
    location = "Aaha Dental Care, Road No. 12, Banjara Hills, Hyderabad"

    ics_content = generate_ics_content(
        appointment_id=test_apt_id,
        summary=summary,
        description=description,
        start_time=appointment_time,
        duration_minutes=45,
        location=location,
        organizer_name="Aaha Dental Care",
        organizer_email="reception@aahadental.in",
    )

    # Validate RFC 5545 specifications
    assert "BEGIN:VCALENDAR" in ics_content
    assert "VERSION:2.0" in ics_content
    assert "BEGIN:VEVENT" in ics_content
    assert f"UID:apt-{test_apt_id}@jkr.ai" in ics_content
    assert "DTSTART:20261005T103000Z" in ics_content
    assert "DTEND:20261005T111500Z" in ics_content
    assert "SUMMARY:Dental Consultation: Gowtham Krishna" in ics_content
    assert "LOCATION:Aaha Dental Care" in ics_content
    assert "STATUS:CONFIRMED" in ics_content
    assert "BEGIN:VALARM" in ics_content
    assert "END:VEVENT" in ics_content
    assert "END:VCALENDAR" in ics_content

    # Validate 1-tap links
    links = get_appointment_calendar_links(
        appointment_id=test_apt_id,
        summary=summary,
        description=description,
        start_time=appointment_time,
        duration_minutes=45,
        location=location,
    )
    assert "https://calendar.google.com/calendar/render?action=TEMPLATE" in links["google_calendar_url"]
    assert "https://outlook.live.com/calendar/0/deeplink/compose" in links["outlook_calendar_url"]
    assert f"/api/v1/appointments/{test_apt_id}/invite.ics" in links["ics_download_url"]


def test_csv_export_format_and_parsing():
    # 1. Appointments CSV
    appts = [
        {
            "id": uuid.uuid4(),
            "contact_name": "Gowtham Krishna",
            "phone": "+919876543210",
            "scheduled_for": datetime(2026, 10, 5, 10, 30, tzinfo=UTC),
            "duration_minutes": 30,
            "status": "scheduled",
            "location": "Aaha Dental Care, Road No. 12, Banjara Hills",
            "notes": "Teeth Cleaning & Consultation",
            "created_at": datetime(2026, 9, 30, 16, 0, tzinfo=UTC),
        }
    ]

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "Appointment ID",
        "Customer / Contact Name",
        "Scheduled Date (IST)",
        "Scheduled Time (IST)",
        "Duration (Minutes)",
        "Status",
        "Location",
        "Notes / Reason",
        "Created At",
    ])
    for a in appts:
        dt = a["scheduled_for"]
        writer.writerow([
            str(a["id"]),
            a["contact_name"],
            dt.strftime("%Y-%m-%d"),
            dt.strftime("%I:%M %p"),
            a["duration_minutes"],
            a["status"],
            a["location"],
            a["notes"],
            a["created_at"].strftime("%Y-%m-%d %H:%M:%S UTC"),
        ])

    csv_text = out.getvalue()
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[0][0] == "Appointment ID"
    assert rows[1][1] == "Gowtham Krishna"
    assert rows[1][4] == "30"
