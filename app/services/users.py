from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import Session
from app.i18n import LANGS
from app.models import User, utcnow
from app.services import settings as rt


def guess_lang(code: str | None) -> str:
    code = (code or "").lower()[:2]
    if code in LANGS:
        return code
    if code in ("kk", "ky", "tg", "be", "uk"):
        return "ru"
    return "uz"


async def upsert(tg_id: int, first_name: str = "", username: str | None = None, lang_code: str | None = None) -> tuple[User, bool]:
    """Create or refresh a user. Returns (user, created).

    Telegram may deliver several updates from a brand-new user at once (they are handled
    concurrently), so a parallel insert can win the race — then we just reload the row.
    """
    for attempt in range(2):
        async with Session() as s:
            u = await s.get(User, tg_id)
            created = u is None
            if created:
                u = User(id=tg_id, lang=guess_lang(lang_code), offsets=list(rt.get("default_offsets")))
                s.add(u)
            u.first_name = (first_name or "")[:128]
            u.username = username
            u.last_seen_at = utcnow()
            u.blocked_bot = False
            if tg_id in get_settings().admin_ids:
                u.is_admin = True
            try:
                await s.commit()
            except IntegrityError:
                if attempt:
                    raise
                continue
            return u, created
    raise RuntimeError("unreachable")


async def get(tg_id: int) -> User | None:
    async with Session() as s:
        return await s.get(User, tg_id)


def is_admin(u: User | None) -> bool:
    return bool(u and (u.is_admin or u.id in get_settings().admin_ids))


async def admin_ids() -> list[int]:
    async with Session() as s:
        ids = set((await s.execute(select(User.id).where(User.is_admin.is_(True)))).scalars().all())
    return sorted(ids | set(get_settings().admin_ids))
