"""Database engine and tables for the Yale SOM course explorer.

One code path, two backends. Locally ``DATABASE_URL`` is unset and we fall back to
the SQLite file the course ships (``data/yale_som.db``). On Render it points at
Supabase Postgres. SQLAlchemy hides the dialect differences, so nothing below
changes between the two.

``courses`` already exists in the shipped file and is read-only here — the model
just mirrors the columns so the search tool can query it. ``users`` and ``chats``
are created on startup if missing.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SQLITE_PATH = ROOT / "data" / "yale_som.db"


def database_url() -> str:
    """Supabase in production, the shipped SQLite file everywhere else."""
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return f"sqlite:///{SQLITE_PATH}"
    # Supabase hands out `postgresql://`, which SQLAlchemy maps to psycopg2. We
    # install psycopg (v3), so name the driver explicitly.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _make_engine():
    url = database_url()
    if url.startswith("sqlite"):
        # check_same_thread=False: FastAPI serves requests on a threadpool, and the
        # default SQLite guard would reject a connection reused across threads.
        return create_engine(url, connect_args={"check_same_thread": False})
    # pool_pre_ping: Supabase drops idle connections; without this the first query
    # after an idle spell fails instead of transparently reconnecting.
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


engine = _make_engine()
IS_SQLITE = database_url().startswith("sqlite")


class Base(DeclarativeBase):
    pass


class Course(Base):
    """Mirror of the shipped ``courses`` table. Read-only from the app's side."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str | None] = mapped_column(Text)
    course_number: Mapped[str | None] = mapped_column(Text)
    course_title: Mapped[str | None] = mapped_column(Text)
    course_category: Mapped[str | None] = mapped_column(Text)
    course_type: Mapped[str | None] = mapped_column(Text)
    course_session: Mapped[str | None] = mapped_column(Text)
    course_description: Mapped[str | None] = mapped_column(Text)
    faculty_1: Mapped[str | None] = mapped_column(Text)
    faculty_1_email: Mapped[str | None] = mapped_column(Text)
    faculty_bio: Mapped[str | None] = mapped_column(Text)
    daytimes: Mapped[str | None] = mapped_column(Text)
    timings_day: Mapped[str | None] = mapped_column(Text)
    timings_start: Mapped[str | None] = mapped_column(Text)
    timings_end: Mapped[str | None] = mapped_column(Text)
    room: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    units: Mapped[str | None] = mapped_column(Text)
    term_code: Mapped[str | None] = mapped_column(Text)
    syllabus: Mapped[str | None] = mapped_column(Text)
    old_syllabus: Mapped[str | None] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Stored lowercased by the auth layer so "Alice" and "alice" are one account.
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chats: Mapped[list["Chat"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Chat(Base):
    """One message. A conversation is every row for a user, ordered by id."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    # Comma-joined tool names for assistant turns; empty for user turns.
    tools_used: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="chats")


def init_db() -> None:
    """Create ``users`` and ``chats`` if absent. Never touches ``courses``."""
    Base.metadata.create_all(engine, tables=[User.__table__, Chat.__table__])


def get_session() -> Session:
    return Session(engine)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
