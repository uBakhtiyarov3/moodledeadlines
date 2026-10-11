from fastapi import Header, HTTPException, Request

from app.config import get_settings
from app.models import User
from app.security import InitDataError, validate_init_data
from app.services import settings as rt
from app.services import users


async def current_user(authorization: str = Header(default="")) -> User:
    """Mini App requests carry `Authorization: tma <Telegram.WebApp.initData>`."""
    scheme, _, init_data = authorization.partition(" ")
    if scheme.lower() != "tma":
        raise HTTPException(401, "missing initData")
    try:
        data = validate_init_data(init_data, get_settings().bot_token)
    except InitDataError as e:
        raise HTTPException(401, str(e)) from e
    tg = data.get("user") or {}
    user, _ = await users.upsert(tg["id"], tg.get("first_name", ""), tg.get("username"), tg.get("language_code"))
    if user.is_banned:
        raise HTTPException(403, "banned")
    if rt.get("maintenance") and not users.is_admin(user):
        raise HTTPException(503, "maintenance")
    return user


async def admin_user(authorization: str = Header(default="")) -> User:
    user = await current_user(authorization)
    if not users.is_admin(user):
        raise HTTPException(403, "admin only")
    return user


def bot(request: Request):
    return request.app.state.bot
