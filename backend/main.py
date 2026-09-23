"""Yale SOM course explorer API desk.

Run from backend/:  uvicorn main:app --reload --port 8000
Open API docs:      http://127.0.0.1:8000/docs
Frontend (Vite):    http://127.0.0.1:5173

Courses come from the ``courses`` table. Everything except /api/health and the two
auth routes requires a bearer token, because the app sits behind a login screen.
"""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select

from agent import run_agent
from auth import MAX_PASSWORD_BYTES, current_user, hash_password, make_token, verify_password
from db import Chat, User, database_url, get_session, init_db
from tools import all_courses

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

# How many past turns to replay into the model. The whole history is always shown
# in the UI; this only bounds what each request costs in tokens.
HISTORY_TURNS = 20


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the users/chats tables before the first request is served."""
    init_db()
    yield


app = FastAPI(title="Yale SOM Courses", version="0.2.0", lifespan=lifespan)


def _allowed_origins() -> list[str]:
    """The deployed frontend's origin(s), set once Render assigns them.

    ``allow_credentials`` with ``["*"]`` is rejected by browsers, so the static
    site's real origin has to be named — hence the env var.
    """
    extra = (os.getenv("FRONTEND_ORIGIN") or "").strip()
    return [o.strip() for o in extra.split(",") if o.strip()]


# Vite picks a different port whenever 5173 is taken, so match localhost on any
# port rather than pinning one. The regex is anchored, so it cannot match a
# hostname that merely starts with "localhost" (e.g. localhost.evil.com).
LOCALHOST_ORIGIN = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=LOCALHOST_ORIGIN,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class Credentials(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        value = value.strip().lower()
        if not USERNAME_RE.match(value):
            raise ValueError(
                "Username must be 3-32 characters, letters/numbers/._- only."
            )
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        # bcrypt truncates (older builds) or raises (newer) past 72 bytes; reject
        # here so a long password can never be silently shortened.
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes."
            )
        return value


class AuthResponse(BaseModel):
    token: str
    username: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    id: int
    role: str
    content: str
    tools_used: list[str] = Field(default_factory=list)
    created_at: str = ""


@app.get("/api/health")
def health():
    return {"ok": True, "backend": "postgres" if "postgresql" in database_url() else "sqlite"}


# ---------------------------------------------------------------- auth


@app.post("/api/auth/signup", response_model=AuthResponse, status_code=201)
def signup(body: Credentials):
    with get_session() as session:
        exists = session.scalar(select(User).where(User.username == body.username))
        if exists is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That username is taken.",
            )
        user = User(
            username=body.username, password_hash=hash_password(body.password)
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return AuthResponse(token=make_token(user), username=user.username)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(body: Credentials):
    with get_session() as session:
        user = session.scalar(select(User).where(User.username == body.username))
        # Same message either way, so the response can't be used to enumerate
        # which usernames exist.
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong username or password.",
            )
        return AuthResponse(token=make_token(user), username=user.username)


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username}


# ---------------------------------------------------------------- courses


@app.get("/api/courses")
def list_courses(
    q: str | None = Query(default=None),
    user: User = Depends(current_user),
):
    """Return courses for the React catalog (optional text filter)."""
    rows = all_courses(q or "")
    return {
        "count": len(rows),
        "courses": [r.model_dump() for r in rows],
    }


# ---------------------------------------------------------------- chat


def _to_message(row: Chat) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        role=row.role,
        content=row.content,
        tools_used=[t for t in (row.tools_used or "").split(",") if t],
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@app.get("/api/chat/history", response_model=list[ChatMessage])
def chat_history(user: User = Depends(current_user)):
    with get_session() as session:
        rows = session.scalars(
            select(Chat).where(Chat.user_id == user.id).order_by(Chat.id)
        ).all()
        return [_to_message(r) for r in rows]


@app.delete("/api/chat/history", status_code=204)
def clear_history(user: User = Depends(current_user)):
    with get_session() as session:
        session.execute(delete(Chat).where(Chat.user_id == user.id))
        session.commit()


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: User = Depends(current_user)):
    with get_session() as session:
        prior = session.scalars(
            select(Chat)
            .where(Chat.user_id == user.id)
            .order_by(Chat.id.desc())
            .limit(HISTORY_TURNS)
        ).all()
        history = [{"role": r.role, "content": r.content} for r in reversed(prior)]

        session.add(Chat(user_id=user.id, role="user", content=body.message))
        session.commit()

    result = run_agent(body.message, history)
    reply = result.get("reply", "")
    tools_used = list(result.get("tools_used") or [])

    with get_session() as session:
        session.add(
            Chat(
                user_id=user.id,
                role="assistant",
                content=reply,
                tools_used=",".join(tools_used),
            )
        )
        session.commit()

    return ChatResponse(reply=reply, tools_used=tools_used)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
