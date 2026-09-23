"""Password hashing and sign-in tokens.

Passwords go through bcrypt, which generates a random salt per password and bakes
it into the hash string — so there is no separate salt column, and two people with
the same password still get different hashes.

Sign-in state is a JWT the browser stores and sends back as `Authorization: Bearer
<token>`. That keeps the backend stateless, which matters on Render's free tier
where the service restarts whenever it idles out (an in-memory session table would
log everyone out on each spin-down).
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from db import User, get_session, utcnow

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=7)

# bcrypt hashes at most 72 bytes and raises on anything longer, so the API rejects
# over-long passwords up front rather than failing inside the hash call.
MAX_PASSWORD_BYTES = 72


def _secret() -> str:
    """Signing key for JWTs.

    In production this must be set — a random per-process fallback would silently
    invalidate every token on restart, and differ across Render instances.
    """
    key = (os.getenv("JWT_SECRET") or "").strip()
    if key:
        return key
    if os.getenv("RENDER") or os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "JWT_SECRET is not set. Add it to the service's environment variables."
        )
    # Local dev only: stable for the life of the process.
    global _DEV_SECRET
    if not _DEV_SECRET:
        _DEV_SECRET = secrets.token_urlsafe(32)
    return _DEV_SECRET


_DEV_SECRET = ""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash in the row — treat as a failed login, not a 500.
        return False


def make_token(user: User) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """FastAPI dependency: resolve the bearer token to a real user row."""
    if creds is None or not creds.credentials:
        raise _UNAUTHORIZED

    try:
        payload = jwt.decode(creds.credentials, _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise _UNAUTHORIZED from None

    user_id = payload.get("sub")
    if not user_id:
        raise _UNAUTHORIZED

    with get_session() as session:
        user = session.scalar(select(User).where(User.id == int(user_id)))
        if user is None:
            # Token is validly signed but the account is gone.
            raise _UNAUTHORIZED
        session.expunge(user)
        return user
