"""FastAPI dependencies: authentication and database access."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from bson import ObjectId

from ..config import config
from ..db import get_db
from ..models import UserRepo

# ── JWT config ────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
# Default 7-day token expiry; set via env var in production
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    __import__("os").environ.get("SURVEY_TOKEN_EXPIRE_MINUTES", "10080")
)
SECRET_KEY = __import__("os").environ.get(
    "SURVEY_JWT_SECRET",
    # Dev-only default — MUST be set via env var in production
    "survey-dev-secret-change-in-production-abc123xyz",
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class TokenData(BaseModel):
    user_id: str


# ── database handle dependency ────────────────────────────────────────────────


def get_db_handle() -> object:
    """Return the current MongoDB database handle.

    Overridden in tests via FastAPI's dependency_overrides mechanism.
    """
    return get_db()


# ── helpers ───────────────────────────────────────────────────────────────────


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _get_current_user(token: Annotated[Optional[str], Depends(oauth2_scheme)]) -> dict:
    """Decode JWT and return the user document; raise 401 if invalid."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user id")

    db = get_db_handle()
    user = UserRepo(db=db).find_by_id(oid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    # strip password_hash before returning
    user.pop("password_hash", None)
    return user


# ── typed dependency aliases ─────────────────────────────────────────────────


CurrentUser = Annotated[dict, Depends(_get_current_user)]
"""The authenticated user document (password_hash removed)."""


def get_db_dep():
    """FastAPI dependency: return the current MongoDB database handle.

    Override this in tests via app.dependency_overrides to use a test database.
    """
    return get_db_handle()


DbDep = Annotated[object, Depends(get_db_dep)]
"""The current MongoDB database handle (FastAPI dependency form)."""

