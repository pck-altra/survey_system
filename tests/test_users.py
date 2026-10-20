"""Tests for app/models/users.py."""
from __future__ import annotations

import pytest
from app.models import UserRepo
from app.models.users import UsernameError, PasswordError


class TestUserRepo:
    def test_create_and_find(self, db):
        repo = UserRepo(db=db)
        uid = repo.create("alice", "password123")
        assert uid is not None

        doc = repo.find_by_username("alice")
        assert doc is not None
        assert doc["username"] == "alice"
        assert "password_hash" in doc
        assert doc["password_hash"] != "password123"

    def test_find_by_id(self, db):
        repo = UserRepo(db=db)
        uid = repo.create("bob", "secret")
        doc = repo.find_by_id(uid)
        assert doc["username"] == "bob"

    def test_create_duplicate_username(self, db):
        repo = UserRepo(db=db)
        repo.create("alice", "password123")
        from pymongo.errors import DuplicateKeyError
        with pytest.raises(DuplicateKeyError):
            repo.create("alice", "anotherpw")

    def test_create_invalid_username_too_short(self, db):
        repo = UserRepo(db=db)
        with pytest.raises(UsernameError):
            repo.create("ab", "pw")

    def test_create_invalid_username_chars(self, db):
        repo = UserRepo(db=db)
        with pytest.raises(UsernameError):
            repo.create("alice-bob", "pw")

    def test_create_invalid_password_too_short(self, db):
        repo = UserRepo(db=db)
        with pytest.raises(PasswordError):
            repo.create("validuser", "12345")

    def test_verify_credentials_correct(self, db):
        repo = UserRepo(db=db)
        repo.create("alice", "password123")
        doc = repo.verify_credentials("alice", "password123")
        assert doc is not None
        assert doc["username"] == "alice"
        assert "password_hash" not in doc  # stripped

    def test_verify_credentials_wrong_password(self, db):
        repo = UserRepo(db=db)
        repo.create("alice", "password123")
        doc = repo.verify_credentials("alice", "wrong")
        assert doc is None

    def test_verify_credentials_unknown_user(self, db):
        repo = UserRepo(db=db)
        doc = repo.verify_credentials("nobody", "any")
        assert doc is None
