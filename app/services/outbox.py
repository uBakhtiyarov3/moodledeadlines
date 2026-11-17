"""A log of every message the agent sends, so an admin can always ask "what did you send?"."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import Session
from app.models import SentMessage, User

SENDING = ("send", "copyMessage", "copyMessages", "forwardMessage", "forwardMessages", "editMessage")


def text_of(params: dict) -> str:
    """The human-readable content of a Bot API request."""
    parts = []
    for key in ("text", "caption", "question", "emoji", "title", "description"):
        if params.get(key):
            parts.append(str(params[key]))
    rich = params.get("rich_message")
    if isinstance(rich, dict):
        parts.append(str(rich.get("markdown") or rich.get("html") or "[rich blocks]"))
    if params.get("options"):
        parts.append("Options: " + " / ".join(str(o.get("text", o)) if isinstance(o, dict) else str(o) for o in params["options"]))
    for media in ("photo", "document", "video", "audio", "voice", "animation", "sticker"):
        if params.get(media):
            parts.append(f"[{media}: {str(params[media])[:200]}]")
    markup = params.get("reply_markup")
    if isinstance(markup, dict) and markup.get("inline_keyboard"):
        labels = [b.get("text", "") for row in markup["inline_keyboard"] for b in row if isinstance(b, dict)]
        parts.append("Buttons: " + " | ".join(labels))
    if params.get("from_chat_id"):
        parts.append(f"[from chat {params['from_chat_id']}, message {params.get('message_id') or params.get('message_ids')}]")
    return "\n".join(parts)


async def log(by: int, via: str, chat_id, text: str) -> None:
    async with Session() as s:
        s.add(SentMessage(by_user_id=by, via=via[:64], chat_id=None if chat_id is None else str(chat_id)[:64], text=(text or "")[:8000]))
        await s.commit()


async def recent(user_id: int | None = None, days: int = 7, limit: int = 50) -> list[dict]:
    from app.services.tasks import local_str

    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(int(days or 7), 365)))
    q = select(SentMessage).where(SentMessage.created_at > since)
    if user_id:
        q = q.where(SentMessage.chat_id == str(user_id))
    async with Session() as s:
        rows = (await s.execute(q.order_by(SentMessage.id.desc()).limit(max(1, min(int(limit or 50), 200))))).scalars().all()
        ids = {int(r.chat_id) for r in rows if r.chat_id and r.chat_id.lstrip("-").isdigit()}
        names = {u.id: u.first_name for u in (await s.execute(select(User).where(User.id.in_(ids)))).scalars()} if ids else {}
    return [{"at": local_str(r.created_at), "to": r.chat_id or "broadcast",
             "to_name": names.get(int(r.chat_id)) if r.chat_id and r.chat_id.lstrip("-").isdigit() else None,
             "via": r.via, "text": r.text} for r in rows]
