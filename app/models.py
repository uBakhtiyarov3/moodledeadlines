from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.db import Base

DEFAULT_OFFSETS = [72 * 60, 24 * 60, 12 * 60, 6 * 60, 3 * 60, 2 * 60, 60]  # minutes


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Always timezone-aware UTC, also on SQLite (which drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            value = value.astimezone(timezone.utc)
            if dialect.name == "sqlite":
                value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user id
    first_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(64))
    lang: Mapped[str] = mapped_column(String(2), default="uz")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)

    # Encrypted Moodle calendar export URL (option A)
    ical_url_enc: Mapped[str | None] = mapped_column(Text)
    # Encrypted Moodle web-service token (option B, optional)
    ws_token_enc: Mapped[str | None] = mapped_column(Text)
    moodle_userid: Mapped[int | None] = mapped_column(Integer)
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_sync_error: Mapped[str | None] = mapped_column(String(255))

    # Notification preferences
    offsets: Mapped[list] = mapped_column(JSON, default=lambda: list(DEFAULT_OFFSETS))
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    muted_courses: Mapped[list] = mapped_column(JSON, default=list)

    ai_used_today: Mapped[int] = mapped_column(Integer, default=0)
    ai_day: Mapped[str] = mapped_column(String(10), default="")

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Deadline(Base):
    __tablename__ = "deadlines"
    __table_args__ = (UniqueConstraint("user_id", "uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    uid: Mapped[str] = mapped_column(String(255))  # iCal UID, e.g. "1234@moodle.uwed.uz"
    moodle_event_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512))
    course: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(1024))
    due_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)

    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    # Event disappeared from the Moodle feed (deleted/moved by teacher)
    gone: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ReminderLog(Base):
    __tablename__ = "reminder_log"
    __table_args__ = (UniqueConstraint("deadline_id", "offset_min", "due_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deadline_id: Mapped[int] = mapped_column(ForeignKey("deadlines.id", ondelete="CASCADE"), index=True)
    offset_min: Mapped[int] = mapped_column(Integer)
    # The due time the reminder was computed for: if the teacher moves the deadline,
    # reminders fire again for the new date.
    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    html: Mapped[str] = mapped_column(Text)
    segment: Mapped[dict] = mapped_column(JSON, default=dict)
    button_text: Mapped[str | None] = mapped_column(String(64))
    button_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued/running/done/failed
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | bool | None] = mapped_column(JSON)
