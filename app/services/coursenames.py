"""Full Moodle course names for the short codes the calendar export uses (e.g. xih_202627).

The calendar only carries the short name. Full names come from the web service whenever a student
with the Moodle Pro connection loads their courses, and are shared: course names aren't private, so
every student of that course then sees the full name.
"""

from sqlalchemy import select

from app.db import Session
from app.models import CourseName, utcnow

_names: dict[str, str] = {}


async def load() -> None:
    async with Session() as s:
        rows = (await s.execute(select(CourseName))).scalars().all()
    _names.clear()
    _names.update({r.shortname: r.fullname for r in rows})


def full(short: str | None) -> str:
    """The full course name if known, else what we were given."""
    return _names.get(short or "", short or "")


def known(short: str) -> bool:
    return short in _names


async def remember(courses) -> None:
    """Store {shortname, fullname} pairs from any Moodle web-service answer."""
    from app.services.coursework import plain

    fresh = {}
    for c in courses or []:
        short, name = (c.get("shortname") or "").strip(), plain(c.get("fullname"), 255)
        if short and name and name != short and _names.get(short) != name:
            fresh[short[:255]] = name
    if not fresh:
        return
    async with Session() as s:
        for short, name in fresh.items():
            await s.merge(CourseName(shortname=short, fullname=name, updated_at=utcnow()))
        await s.commit()
    _names.update(fresh)
