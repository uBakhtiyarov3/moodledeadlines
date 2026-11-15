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


class SupportMessage(Base):
    """Student ↔ admin conversation (one thread per student)."""

    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    from_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_id: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    # read by the other side (student reads admin messages and vice versa)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


class SupportState(Base):
    """Who is "talking to admin" right now (students) / replying to whom (admins)."""

    __tablename__ = "support_state"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mode: Mapped[str] = mapped_column(String(16))  # "chat" (student) | "reply" (admin)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SupportRelay(Base):
    """Maps a student message delivered to an admin's chat → the student, for native replies."""

    __tablename__ = "support_relay"
    __table_args__ = (UniqueConstraint("admin_id", "message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(BigInteger)


class Profile(Base):
    """What the AI knows about a student: names, study details they entered and remembered facts.

    A separate table (not columns on users) so existing databases get it without a migration.
    """

    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_name: Mapped[str] = mapped_column(String(128), default="")
    moodle_name: Mapped[str] = mapped_column(String(255), default="")  # full name from Moodle (account link)
    faculty: Mapped[str] = mapped_column(String(160), default="")
    year: Mapped[str] = mapped_column(String(16), default="")  # "1".."4" | "master"
    group_name: Mapped[str] = mapped_column(String(64), default="")
    about: Mapped[str] = mapped_column(Text, default="")
    memory: Mapped[list] = mapped_column(JSON, default=list)  # short facts learned from chats
    memory_on: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Task(Base):
    """Something the assistant does later for a user: a reminder, an agent run or a scheduled broadcast."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # "reminder" | "agent" | "broadcast"
    text: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # broadcast: segment / button
    run_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    repeat: Mapped[str] = mapped_column(String(16), default="")  # "" | daily | weekdays | weekly
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class PendingAction(Base):
    """A high-impact agent action waiting for the user's ✅ (broadcast, ban, delete…)."""

    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | done | cancelled | failed
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AgentButton(Base):
    """A quick-reply button the assistant put under a message: tapping it 'says' this text."""

    __tablename__ = "agent_buttons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class GradeSeen(Base):
    """Last grade/feedback we saw for a Moodle grade item, to notify only about changes."""

    __tablename__ = "grades_seen"
    __table_args__ = (UniqueConstraint("user_id", "item_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_key: Mapped[str] = mapped_column(String(64))  # "<courseid>:<gradeitemid>"
    name: Mapped[str] = mapped_column(String(255), default="")
    fingerprint: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class HiddenCourse(Base):
    """A Moodle course the student hid: off the grades page, its deadlines and reminders."""

    __tablename__ = "hidden_courses"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(Integer)
    fullname: Mapped[str] = mapped_column(String(255), default="")
    shortname: Mapped[str] = mapped_column(String(255), default="")
