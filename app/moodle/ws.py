"""Optional Moodle account connection (option B) via the Moodle Mobile web service.

The password is exchanged once for a web-service token and is never stored.
The token is used to learn which tracked events are *already done*: Moodle's
`core_calendar_get_action_events_by_timesort` only returns events the student still
has to act on (a submitted assignment or finished quiz disappears from it).
"""

from datetime import datetime, timezone

import httpx

from app.config import get_settings


class MoodleAuthError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def get_token(username: str, password: str) -> str:
    base = get_settings().moodle_base.rstrip("/")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{base}/login/token.php",
            data={"username": username, "password": password, "service": "moodle_mobile_app"},
        )
    data = r.json()
    if "token" not in data:
        raise MoodleAuthError(data.get("errorcode") or "unknown")
    return data["token"]


async def call(token: str, function: str, **params) -> dict | list:
    base = get_settings().moodle_base.rstrip("/")
    payload = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json", **params}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{base}/webservice/rest/server.php", data=payload)
    data = r.json()
    if isinstance(data, dict) and data.get("exception"):
        raise MoodleAuthError(data.get("errorcode") or "ws_error")
    return data


async def site_userid(token: str) -> int:
    info = await call(token, "core_webservice_get_site_info")
    return int(info["userid"])


async def pending_action_event_ids(token: str, days_ahead: int = 90) -> set[int]:
    """Ids of calendar events that still require an action from the student."""
    now = int(datetime.now(timezone.utc).timestamp())
    ids: set[int] = set()
    after_id = 0
    for _ in range(10):  # paginate, max 500 events
        params = {"timesortfrom": now - 6 * 3600, "timesortto": now + days_ahead * 86400, "limitnum": 50}
        if after_id:
            params["aftereventid"] = after_id
        data = await call(token, "core_calendar_get_action_events_by_timesort", **params)
        events = data.get("events", []) if isinstance(data, dict) else []
        # Presence alone means "still to do": an item that is not yet actionable
        # (e.g. assignment not open yet) is still pending.
        ids.update(int(e["id"]) for e in events)
        if len(events) < 50:
            break
        after_id = int(events[-1]["id"])
    return ids
