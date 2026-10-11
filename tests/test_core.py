import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest

from app.models import Deadline
from app.moodle.ical import IcalUrlError, normalize_export_url, parse_ical
from app.security import InitDataError, decrypt, encrypt, validate_init_data
from app.services.kb import Index
from app.services.reminders import plan_reminder
from app.services.sync import merge_events
from app.services.tg_html import markdown_to_tg, sanitize

BASE = "https://moodle.uwed.uz"
TOKEN = "a" * 32
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
OFFSETS = [4320, 1440, 720, 360, 180, 120, 60]

ICS = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Moodle Pty Ltd//NONSGML Moodle Version 2024100700//EN
BEGIN:VEVENT
UID:4321@moodle.uwed.uz
SUMMARY:Essay 2 is due
DESCRIPTION:<p>Write 1500 words</p>
CLASS:PUBLIC
LAST-MODIFIED:20261001T100000Z
DTSTAMP:20261011T100000Z
DTSTART:20261014T185900Z
DTEND:20261014T185900Z
CATEGORIES:International Relations 101
END:VEVENT
BEGIN:VEVENT
UID:4322@moodle.uwed.uz
SUMMARY:Quiz 3 closes
DTSTAMP:20261011T100000Z
DTSTART;VALUE=DATE:20261020
END:VEVENT
END:VCALENDAR
"""


# --- export URL ---------------------------------------------------------------

def test_normalize_forces_all_and_upcoming():
    raw = f"{BASE}/calendar/export_execute.php?userid=77&authtoken={TOKEN}&preset_what=user&preset_time=weeknow"
    out = normalize_export_url(raw, BASE)
    assert "preset_what=all" in out and "preset_time=recentupcoming" in out and "userid=77" in out


def test_normalize_accepts_webcal():
    out = normalize_export_url(f"webcal://moodle.uwed.uz/calendar/export_execute.php?userid=1&authtoken={TOKEN}", BASE)
    assert out.startswith("https://moodle.uwed.uz/")


@pytest.mark.parametrize(
    "url,code",
    [
        (f"https://evil.example/calendar/export_execute.php?userid=1&authtoken={TOKEN}", "wrong_host"),
        (f"{BASE}/calendar/export.php", "not_export"),
        (f"{BASE}/calendar/export_execute.php?userid=1", "no_token"),
        (f"http://169.254.169.254/calendar/export_execute.php?userid=1&authtoken={TOKEN}", "wrong_host"),
    ],
)
def test_normalize_rejects(url, code):
    with pytest.raises(IcalUrlError) as e:
        normalize_export_url(url, BASE)
    assert e.value.args[0] == code


# --- iCal parsing -------------------------------------------------------------

def test_parse_ical():
    events = parse_ical(ICS, BASE)
    assert len(events) == 2
    e = events[0]
    assert e.uid == "4321@moodle.uwed.uz" and e.moodle_event_id == 4321
    assert e.title == "Essay 2 is due"
    assert e.course == "International Relations 101"
    assert e.description == "Write 1500 words"
    assert e.due_at == datetime(2026, 10, 14, 18, 59, tzinfo=timezone.utc)
    assert e.url.endswith("#event_4321")
    assert events[1].due_at.tzinfo is not None


def test_merge_marks_gone_and_updates():
    events = parse_ical(ICS, BASE)
    new, _ = merge_events({}, events, 1, NOW)
    assert len(new) == 2
    existing = {d.uid: d for d in new}
    for d in new:
        d.gone = False
    # teacher moves essay by a day and deletes the quiz
    moved = [events[0]]
    moved[0].due_at += timedelta(days=1)
    new2, changed = merge_events(existing, moved, 1, NOW)
    assert not new2 and changed == 2
    assert existing["4322@moodle.uwed.uz"].gone is True
    assert existing["4321@moodle.uwed.uz"].due_at == datetime(2026, 10, 15, 18, 59, tzinfo=timezone.utc)


# --- reminder planning --------------------------------------------------------

def test_nothing_before_first_threshold():
    assert plan_reminder(NOW + timedelta(days=5), NOW, OFFSETS, set()).send is None


def test_three_day_reminder():
    p = plan_reminder(NOW + timedelta(hours=71, minutes=59), NOW, OFFSETS, set())
    assert p.send == 4320 and p.skip == ()


def test_late_discovery_sends_only_tightest():
    p = plan_reminder(NOW + timedelta(hours=5), NOW, OFFSETS, set())
    assert p.send == 360
    assert set(p.skip) == {4320, 1440, 720}


def test_already_sent_not_repeated():
    p = plan_reminder(NOW + timedelta(hours=5), NOW, OFFSETS, {4320, 1440, 720, 360})
    assert p.send is None


def test_respects_user_offsets():
    p = plan_reminder(NOW + timedelta(minutes=50), NOW, [1440, 60], {1440})
    assert p.send == 60


def test_past_deadline_never_sends():
    assert plan_reminder(NOW - timedelta(minutes=1), NOW, OFFSETS, set()).send is None


# --- Telegram initData --------------------------------------------------------

def _sign(fields: dict, bot_token: str) -> str:
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})


def test_init_data_valid_and_tampered():
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 5, "first_name": "Ali"})}
    data = validate_init_data(_sign(fields, "123:ABC"), "123:ABC")
    assert data["user"]["id"] == 5
    with pytest.raises(InitDataError):
        validate_init_data(_sign(fields, "123:ABC"), "999:XYZ")
    with pytest.raises(InitDataError):
        validate_init_data(_sign(fields, "123:ABC").replace("Ali", "Bob"), "123:ABC")


def test_init_data_expired():
    fields = {"auth_date": str(int(time.time()) - 10 * 86400), "user": json.dumps({"id": 5})}
    with pytest.raises(InitDataError):
        validate_init_data(_sign(fields, "1:A"), "1:A")


def test_encrypt_roundtrip():
    assert decrypt(encrypt("secret")) == "secret"
    assert decrypt("garbage") is None


# --- rich text ----------------------------------------------------------------

def test_sanitize_editor_html():
    src = (
        '<div><b>Salom</b> <i>talabalar</i>!</div><div><span class="tg-spoiler">sir</span> '
        '<a href="https://uwed.uz">sayt</a> <a href="javascript:alert(1)">x</a></div>'
        "<ul><li>bir</li><li>ikki</li></ul><script>alert(1)</script><img src=x onerror=alert(1)>"
    )
    out = sanitize(src)
    assert "<b>Salom</b>" in out and "<i>talabalar</i>" in out
    assert "<tg-spoiler>sir</tg-spoiler>" in out
    assert '<a href="https://uwed.uz">sayt</a>' in out
    assert "javascript" not in out and "<script" not in out and "<img" not in out
    assert "• bir\n• ikki" in out


def test_sanitize_escapes_text():
    assert sanitize("a < b & c") == "a &lt; b &amp; c"


def test_markdown_to_tg():
    out = markdown_to_tg("**Muhim**: *diqqat* `code` <x>\n- bir")
    assert out == "<b>Muhim</b>: <i>diqqat</i> <code>code</code> &lt;x&gt;\n• bir"


# --- knowledge base -----------------------------------------------------------

def test_kb_search_multilingual():
    idx = Index(
        [
            ("Kontrakt to'lovi", "Kontrakt to'lovi har semestr boshida amalga oshiriladi. Bank rekvizitlari dekanatda."),
            ("Библиотека", "Библиотека работает с 9:00 до 18:00, читальный зал на втором этаже."),
            ("Exams", "Final exams are held in January and June according to the schedule."),
        ]
    )
    assert idx.search("kontrakt to'lovini qachon to'lash kerak")[0].doc_title == "Kontrakt to'lovi"
    assert idx.search("когда работает библиотека")[0].doc_title == "Библиотека"
    assert idx.search("when are the final exams")[0].doc_title == "Exams"
    assert idx.search("zzzz") == []


def test_deadline_model_defaults_import():
    assert Deadline.__tablename__ == "deadlines"


def test_markdown_to_tg_telegram_features():
    md = (
        "📌 **Reja**\n\n1. **Kirish**\n   - ichki *band*\n- ~~eski~~ ||javob||\n"
        "> birinchi\n> ikkinchi\n\n`a < b`\n```\nx = 1 * 2 * 3\n```\n## Sarlavha\n| A | B |\n|---|---|\n---\nsnake_case_name"
    )
    out = markdown_to_tg(md)
    assert "📌 <b>Reja</b>" in out
    assert "    ◦ ichki <i>band</i>" in out
    assert "• <s>eski</s> <tg-spoiler>javob</tg-spoiler>" in out
    assert "<blockquote>birinchi\nikkinchi</blockquote>" in out
    assert "<code>a &lt; b</code>" in out and "<pre>x = 1 * 2 * 3</pre>" in out
    assert "<b>Sarlavha</b>" in out and "A · B" in out and "---" not in out
    assert "snake_case_name" in out
    long_quote = markdown_to_tg("\n".join(f"> {i}" for i in range(6)))
    assert long_quote.startswith("<blockquote expandable>")
