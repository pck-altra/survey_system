"""API integration tests using FastAPI TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from bson import ObjectId

from app.main import app
from app import get_db, reset_client, ensure_indexes
from app.config import config


@pytest.fixture(scope="function")
def client():
    """Isolated test database + TestClient.

    Each test gets its own isolated MongoDB database so tests never interfere
    with each other.  We achieve this by:

    1. reset_client()      — close the existing singleton
    2. config.MONGO_DB    — point the config at the fresh test database name
    3. ensure_indexes()   — create indexes on the test database
       (get_db() inside ensure_indexes reads config.MONGO_DB which we just set)
    """
    test_db_name = f"survey_system_test_{ObjectId()}"

    reset_client()
    original_db = config.MONGO_DB
    config.MONGO_DB = test_db_name

    db = get_db()   # reads config.MONGO_DB (= test_db_name) → test database
    ensure_indexes(db)

    with TestClient(app) as c:
        yield c

    config.MONGO_DB = original_db
    reset_client()


@pytest.fixture
def registered_user(client):
    """Register a user and return (username, password)."""
    resp = client.post("/api/auth/register", json={"username": "testuser", "password": "password123"})
    assert resp.status_code == 201
    return {"username": "testuser", "password": "password123"}


@pytest.fixture
def auth_headers(client, registered_user):
    """Return a dict of auth headers for the registered user."""
    resp = client.post(
        "/api/auth/login",
        params={"username": registered_user["username"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAuthAPI:
    def test_register_ok(self, client):
        resp = client.post("/api/auth/register", json={"username": "alice2", "password": "secret123"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "alice2"
        assert "id" in data

    def test_register_duplicate(self, client, registered_user):
        resp = client.post(
            "/api/auth/register",
            json={"username": registered_user["username"], "password": "anotherpw"},
        )
        assert resp.status_code == 409

    def test_login_ok(self, client, registered_user):
        resp = client.post(
            "/api/auth/login",
            params={"username": registered_user["username"], "password": registered_user["password"]},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client, registered_user):
        resp = client.post(
            "/api/auth/login",
            params={"username": registered_user["username"], "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_me(self, client, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"


class TestSurveyAPI:
    def test_create_survey(self, client, auth_headers):
        resp = client.post(
            "/api/surveys/",
            json={"title": "My Survey", "description": "A test survey", "allow_anonymous": False},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My Survey"
        assert data["status"] == "draft"
        assert data["token"] is None

    def test_list_surveys(self, client, auth_headers):
        client.post("/api/surveys/", json={"title": "S1"}, headers=auth_headers)
        client.post("/api/surveys/", json={"title": "S2"}, headers=auth_headers)
        resp = client.get("/api/surveys/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_publish_survey(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Pub Survey"}, headers=auth_headers)
        sid = create.json()["id"]
        resp = client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"
        assert resp.json()["token"] is not None

    def test_get_survey_by_token(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Token Survey"}, headers=auth_headers)
        sid = create.json()["id"]
        pub = client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        token = pub.json()["token"]
        resp = client.get(f"/api/surveys/token/{token}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Token Survey"

    def _make_published_survey(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "S"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        return sid

    def test_delete_survey(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Delete Me"}, headers=auth_headers)
        sid = create.json()["id"]
        resp = client.delete(f"/api/surveys/{sid}", headers=auth_headers)
        assert resp.status_code == 204

    def test_cannot_delete_published_survey(self, client, auth_headers):
        sid = self._make_published_survey(client, auth_headers)
        resp = client.delete(f"/api/surveys/{sid}", headers=auth_headers)
        assert resp.status_code == 422


class TestQuestionAPI:
    def _make_published_survey(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Q Survey"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        return sid

    def test_add_question(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Q Survey"}, headers=auth_headers)
        sid = create.json()["id"]
        resp = client.post(
            f"/api/surveys/{sid}/questions",
            json={
                "type": "single",
                "title": "Gender?",
                "options": ["男", "女"],
                "required": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "single"
        assert data["order"] == 1
        assert data["options"] == ["男", "女"]

    def test_cannot_add_question_to_published(self, client, auth_headers):
        sid = self._make_published_survey(client, auth_headers)
        resp = client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "text", "title": "Too late"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_delete_question(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Del Q"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "text", "title": "Will be deleted"},
            headers=auth_headers,
        )
        resp = client.delete(f"/api/surveys/{sid}/questions/1", headers=auth_headers)
        assert resp.status_code == 204

    def test_update_question(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Upd Q"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "Old title", "options": ["A", "B"]},
            headers=auth_headers,
        )
        resp = client.put(
            f"/api/surveys/{sid}/questions/1",
            json={"title": "New title", "options": ["A", "B", "C"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New title"
        assert data["options"] == ["A", "B", "C"]

    def test_update_question_not_owner(self, client, auth_headers):
        # register and login as another user to get a separate token
        client.post("/api/auth/register", json={"username": "user2b", "password": "pass123"})
        resp2 = client.post(
            "/api/auth/login",
            params={"username": "user2b", "password": "pass123"},
        )
        other_token = resp2.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        create = client.post("/api/surveys/", json={"title": "Upd Q"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "text", "title": "Q1"},
            headers=auth_headers,
        )
        resp = client.put(
            f"/api/surveys/{sid}/questions/1",
            json={"title": "Hacked"},
            headers=other_headers,
        )
        assert resp.status_code == 403

    def test_update_question_draft_only(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Pub Q"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "text", "title": "Q1"},
            headers=auth_headers,
        )
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        resp = client.put(
            f"/api/surveys/{sid}/questions/1",
            json={"title": "Should fail"},
            headers=auth_headers,
        )
        assert resp.status_code == 422


class TestSubmissionAPI:
    def test_start_submission_requires_auth(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Sub Survey"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "Gender?", "options": ["男", "女"]},
            headers=auth_headers,
        )
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        # No auth → 401
        resp = client.post(f"/api/surveys/{sid}/submit/start")
        assert resp.status_code == 401

    def test_start_submission(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Sub Survey", "allow_anonymous": True}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "Gender?", "options": ["男", "女"]},
            headers=auth_headers,
        )
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        resp = client.post(f"/api/surveys/{sid}/submit/start", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "submission_id" in data
        assert data["next_order"] == 1

    def test_submit_answer(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Ans Survey", "allow_anonymous": True}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "Gender?", "options": ["男", "女"]},
            headers=auth_headers,
        )
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        start = client.post(f"/api/surveys/{sid}/submit/start", headers=auth_headers).json()
        sid2 = start["submission_id"]
        resp = client.post(
            f"/api/surveys/{sid}/submit/{sid2}/answer",
            json={"question_order": 1, "value": "男"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_end"] is True

    def test_finalize_submission_requires_owner(self, client, auth_headers):
        """Finalize must be called by the same user that started the submission."""
        create = client.post("/api/surveys/", json={"title": "Fin Survey"}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "Gender?", "options": ["男", "女"]},
            headers=auth_headers,
        )
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        start = client.post(f"/api/surveys/{sid}/submit/start", headers=auth_headers).json()
        sub_id = start["submission_id"]
        client.post(
            f"/api/surveys/{sid}/submit/{sub_id}/answer",
            json={"question_order": 1, "value": "女"},
            headers=auth_headers,
        )
        # Register a second user; they cannot finalize someone else's submission.
        client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "password123"},
        )
        bob_login = client.post(
            "/api/auth/login",
            params={"username": "bob", "password": "password123"},
        ).json()
        bob_headers = {"Authorization": f"Bearer {bob_login['access_token']}"}
        resp = client.post(
            f"/api/surveys/{sid}/submit/{sub_id}/finalize",
            headers=bob_headers,
        )
        assert resp.status_code == 403

    def test_finalize_submission(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Fin Survey", "allow_anonymous": True}, headers=auth_headers)
        sid = create.json()["id"]
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "Gender?", "options": ["男", "女"]},
            headers=auth_headers,
        )
        client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        start = client.post(f"/api/surveys/{sid}/submit/start", headers=auth_headers).json()
        sub_id = start["submission_id"]
        client.post(
            f"/api/surveys/{sid}/submit/{sub_id}/answer",
            json={"question_order": 1, "value": "女"},
            headers=auth_headers,
        )
        resp = client.post(f"/api/surveys/{sid}/submit/{sub_id}/finalize", headers=auth_headers)
        assert resp.status_code == 200
        assert "submitted_at" in resp.json()


class TestStatisticsAPI:
    def test_statistics_requires_owner(self, client, auth_headers):
        create = client.post("/api/surveys/", json={"title": "Stat Survey", "allow_anonymous": True}, headers=auth_headers)
        assert create.status_code == 201, f"create failed {create.status_code}: {create.json()}"
        sid = create.json()["id"]
        r = client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "Gender?", "options": ["男", "女"]},
            headers=auth_headers,
        )
        assert r.status_code == 201, f"add question failed {r.status_code}: {r.json()}"
        r = client.post(f"/api/surveys/{sid}/publish", headers=auth_headers)
        assert r.status_code == 200, f"publish failed {r.status_code}: {r.json()}"
        start = client.post(f"/api/surveys/{sid}/submit/start", headers=auth_headers)
        assert start.status_code == 200, f"start failed {start.status_code}: {start.json()}"
        start_data = start.json()
        assert "submission_id" in start_data, f"no submission_id: {start_data}"
        sub_id = start_data["submission_id"]
        r = client.post(
            f"/api/surveys/{sid}/submit/{sub_id}/answer",
            json={"question_order": 1, "value": "男"},
            headers=auth_headers,
        )
        assert r.status_code == 200, f"answer failed {r.status_code}: {r.json()}"
        r = client.post(f"/api/surveys/{sid}/submit/{sub_id}/finalize", headers=auth_headers)
        assert r.status_code == 200, f"finalize failed {r.status_code}: {r.json()}"
        resp = client.get(f"/api/surveys/{sid}/statistics", headers=auth_headers)
        assert resp.status_code == 200, f"stats failed {resp.status_code}: {resp.json()}"
        data = resp.json()
        assert data["total_submissions"] == 1
        assert len(data["single_choice"]) == 1
        assert data["single_choice"][0]["total"] == 1
