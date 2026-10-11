"""Moodle calendar export (iCal) URL handling and parsing."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from icalendar import Calendar

from app.config import get_settings


class IcalUrlError(ValueError):
    """Raised with a machine readable code: wrong_host / no_token / not_export."""


@dataclass
class ParsedEvent:
    uid: str
    moodle_event_id: int | None
    title: str
    course: str
    description: str
    due_at: datetime
    url: str


def normalize_export_url(raw: str, moodle_base: str | None = None) -> str:
    """Validate a user supplied export URL and rebuild it so it always covers all courses
    and the widest upcoming window Moodle offers (recent + next 60 days).

    Only the configured Moodle host is accepted (prevents the bot being used as an SSRF proxy).
    """
    base = urlparse(moodle_base or get_settings().moodle_base)
    raw = raw.strip()
    if raw.startswith("webcal://"):
        raw = "https://" + raw[len("webcal://") :]
    u = urlparse(raw)
    if u.scheme not in ("http", "https") or u.hostname != base.hostname:
        raise IcalUrlError("wrong_host")
    if not u.path.rstrip("/").endswith("/calendar/export_execute.php"):
        raise IcalUrlError("not_export")
    q = parse_qs(u.query)
    userid = (q.get("userid") or [""])[0]
    token = (q.get("authtoken") or [""])[0]
    if not userid.isdigit() or not re.fullmatch(r"[0-9a-fA-F]{20,64}", token):
        raise IcalUrlError("no_token")
    query = urlencode(
        {"userid": userid, "authtoken": token, "preset_what": "all", "preset_time": "recentupcoming"}
    )
    return f"https://{base.hostname}/calendar/export_execute.php?{query}"


def userid_from_url(url: str) -> int | None:
    v = (parse_qs(urlparse(url).query).get("userid") or [""])[0]
    return int(v) if v.isdigit() else None


async def fetch_ical(url: str, client: httpx.AsyncClient | None = None) -> str:
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=False)
    try:
        r = await client.get(url, headers={"User-Agent": "UWED-StudentBot/1.0"})
        r.raise_for_status()
        text = r.text
        if "BEGIN:VCALENDAR" not in text:
            # Moodle answers "Invalid authentication" with HTTP 200 for a bad token
            raise IcalUrlError("bad_token")
        return text
    finally:
        if own:
            await client.aclose()


def _to_utc(v) -> datetime:
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
    if isinstance(v, date):
        return datetime.combine(v, time(23, 59), tzinfo=timezone.utc)
    raise ValueError(f"unsupported date {v!r}")


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_ical(text: str, moodle_base: str | None = None) -> list[ParsedEvent]:
    base = (moodle_base or get_settings().moodle_base).rstrip("/")
    cal = Calendar.from_ical(text)
    events: list[ParsedEvent] = []
    for comp in cal.walk("VEVENT"):
        uid = str(comp.get("UID", "")).strip()
        dt = comp.get("DTSTART")
        if not uid or dt is None:
            continue
        due = _to_utc(dt.dt)
        # Moodle puts the course name into CATEGORIES
        course = ""
        cats = comp.get("CATEGORIES")
        if cats is not None:
            cats_list = cats if isinstance(cats, list) else [cats]
            names = [str(c) for cat in cats_list for c in getattr(cat, "cats", [cat])]
            course = ", ".join(n for n in names if n)
        m = re.match(r"(\d+)@", uid)
        event_id = int(m.group(1)) if m else None
        ts = int(due.timestamp())
        url = f"{base}/calendar/view.php?view=day&time={ts}"
        if event_id:
            url += f"#event_{event_id}"
        events.append(
            ParsedEvent(
                uid=uid,
                moodle_event_id=event_id,
                title=_clean(str(comp.get("SUMMARY", "")))[:500] or "—",
                course=course[:250],
                description=_clean(str(comp.get("DESCRIPTION", "")))[:2000],
                due_at=due,
                url=url,
            )
        )
    return events
