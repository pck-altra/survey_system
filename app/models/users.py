"""`users` collection repository.

Implements docs/数据库设计.md §4.1:

* ``username``  : unique, 3-32 chars, regex ``^[A-Za-z0-9_]+$``
* ``password_hash`` : bcrypt with cost=12
* ``created_at`` : UTC datetime
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Optional

import bcrypt
from pymongo.collection import Collection

from ..config import config
from ..db import get_db

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


class UsernameError(ValueError):
    """Raised when a username fails the schema rules."""


class PasswordError(ValueError):
    """Raised when a password fails the schema rules."""


def _hash_password(plain: str) -> str:
    """Hash with bcrypt at the configured cost."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=config.BCRYPT_COST)).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _validate_username(username: str) -> None:
    if not isinstance(username, str) or len(username) < 3 or len(username) > 32:
        raise UsernameError("username must be 3-32 characters")
    if not _USERNAME_RE.match(username):
        raise UsernameError("username may only contain letters, digits, and underscores")


def _validate_password(plain: str) -> None:
    if not isinstance(plain, str) or len(plain) < 6:
        raise PasswordError("password must be at least 6 characters")
    if len(plain) > 200:
        raise PasswordError("password too long (max 200)")


class UserRepo:
    """Data-access object for the ``users`` collection."""

    def __init__(self, db=None):
        self._db = db if db is not None else get_db()
        self._coll: Collection = self._db["users"]

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------

    def create(self, username: str, password: str) -> str:
        """Create a user and return the inserted ``_id``.

        Raises
        ------
        UsernameError / PasswordError
            on invalid input.
        pymongo.errors.DuplicateKeyError
            if the username already exists.
        """
        _validate_username(username)
        _validate_password(password)

        doc: dict[str, Any] = {
            "username": username,
            "password_hash": _hash_password(password),
            "created_at": dt.datetime.now(dt.timezone.utc),
        }
        return self._coll.insert_one(doc).inserted_id

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def find_by_username(self, username: str) -> Optional[dict]:
        return self._coll.find_one({"username": username})

    def find_by_id(self, user_id) -> Optional[dict]:
        return self._coll.find_one({"_id": user_id})

    # ------------------------------------------------------------------
    # auth helpers
    # ------------------------------------------------------------------

    def verify_credentials(self, username: str, password: str) -> Optional[dict]:
        """Return the user document if the credentials are valid, else ``None``."""
        doc = self.find_by_username(username)
        if doc is None:
            return None
        if not _verify_password(password, doc["password_hash"]):
            return None
        # strip secret before returning
        doc.pop("password_hash", None)
        return doc
