"""题库 / 可复用题目 / 版本历史 / 共享 / 跨问卷统计 的 API 测试。

覆盖《需求变更说明》中的八条需求。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from bson import ObjectId

from app.main import app
from tests.conftest import clean_collections


@pytest.fixture(scope="module")
def _api_client(session_db):
    """整个模块共用会话级测试库与 TestClient。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def client(_api_client, session_db):
    # 用例之间清空数据（保留集合与索引，避免反复创建文件）
    clean_collections(session_db)
    yield _api_client


def _login(client, username: str, password: str = "password123") -> dict:
    client.post("/api/auth/register", json={"username": username, "password": password})
    resp = client.post(
        "/api/auth/login", params={"username": username, "password": password}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def owner(client):
    return _login(client, "teacher")


@pytest.fixture
def student(client):
    return _login(client, "student")


def _make_survey(client, headers, title="S"):
    resp = client.post("/api/surveys/", json={"title": title}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_bank_question(client, headers, **overrides):
    payload = {
        "type": "single",
        "title": "你的年龄",
        "options": ["18岁以下", "18-25岁", "26岁以上"],
        "tags": ["人口学"],
    }
    payload.update(overrides)
    resp = client.post("/api/bank/questions", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── 需求一：保存常用题目 ──────────────────────────────────────────────────────


class TestSaveReusableQuestion:
    def test_create_and_list(self, client, owner):
        q = _make_bank_question(client, owner)
        assert q["version"] == 1
        assert q["title"] == "你的年龄"
        assert q["in_bank"] is True
        assert q["tags"] == ["人口学"]
        assert q["can_edit"] is True

        resp = client.get("/api/bank/questions", headers=owner)
        assert resp.status_code == 200
        titles = [x["title"] for x in resp.json()]
        assert "你的年龄" in titles

    def test_keyword_filter(self, client, owner):
        _make_bank_question(client, owner, title="你的年龄")
        _make_bank_question(client, owner, title="你的性别", options=["男", "女"])
        resp = client.get("/api/bank/questions", params={"keyword": "年龄"}, headers=owner)
        assert resp.status_code == 200
        assert [x["title"] for x in resp.json()] == ["你的年龄"]

    def test_text_question_has_no_options(self, client, owner):
        q = _make_bank_question(client, owner, type="text", title="意见", options=None)
        assert q["options"] is None


# ── 需求二：分享题目给其他用户 ────────────────────────────────────────────────


class TestShareQuestion:
    def test_share_with_user(self, client, owner, student):
        q = _make_bank_question(client, owner)
        resp = client.post(
            f"/api/bank/questions/{q['id']}/share",
            json={"usernames": ["student"]},
            headers=owner,
        )
        assert resp.status_code == 200
        assert resp.json()["shared_with"] == ["student"]

        # 学生可以看到该题目
        lst = client.get("/api/bank/questions", headers=student)
        assert lst.status_code == 200
        assert any(x["title"] == "你的年龄" for x in lst.json())
        # 但不能编辑
        assert all(not x["can_edit"] for x in lst.json() if x["title"] == "你的年龄")

    def test_public_visibility(self, client, owner, student):
        q = _make_bank_question(client, owner)
        resp = client.post(
            f"/api/bank/questions/{q['id']}/share",
            json={"visibility": "public"},
            headers=owner,
        )
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "public"

        lst = client.get("/api/bank/questions", headers=student)
        assert any(x["title"] == "你的年龄" for x in lst.json())

    def test_other_user_cannot_share(self, client, owner, student):
        q = _make_bank_question(client, owner)
        client.post(
            f"/api/bank/questions/{q['id']}/share",
            json={"usernames": ["student"]},
            headers=owner,
        )
        resp = client.post(
            f"/api/bank/questions/{q['id']}/share",
            json={"visibility": "public"},
            headers=student,
        )
        assert resp.status_code == 403

    def test_student_can_use_shared_question_in_own_survey(self, client, owner, student):
        q = _make_bank_question(client, owner)
        client.post(
            f"/api/bank/questions/{q['id']}/share",
            json={"usernames": ["student"]},
            headers=owner,
        )
        sid = _make_survey(client, student, "学生的问卷")
        resp = client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "ignored", "bank_question_id": q["id"]},
            headers=student,
        )
        assert resp.status_code == 201
        data = resp.json()
        # 内容以题库题目为准
        assert data["title"] == "你的年龄"
        assert data["options"] == ["18岁以下", "18-25岁", "26岁以上"]
        assert data["bank_ref"]["version_id"] == q["id"]

    def test_use_bank_question_without_type_and_title(self, client, owner):
        """前端「从题库选择」只提交 bank_question_id，后端应自动补全内容。"""
        q = _make_bank_question(client, owner)
        sid = _make_survey(client, owner, "问卷B")
        resp = client.post(
            f"/api/surveys/{sid}/questions",
            json={"bank_question_id": q["id"]},
            headers=owner,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "你的年龄"
        assert data["type"] == "single"
        assert data["options"] == ["18岁以下", "18-25岁", "26岁以上"]
        assert data["bank_ref"]["version_id"] == q["id"]

    def test_question_without_type_title_or_bank_is_rejected(self, client, owner):
        sid = _make_survey(client, owner, "问卷C")
        resp = client.post(
            f"/api/surveys/{sid}/questions",
            json={"required": True},
            headers=owner,
        )
        assert resp.status_code == 422

    def test_student_cannot_use_private_question(self, client, owner, student):
        q = _make_bank_question(client, owner)
        sid = _make_survey(client, student, "S")
        resp = client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "x", "bank_question_id": q["id"]},
            headers=student,
        )
        assert resp.status_code == 403

    def test_fork_shared_question(self, client, owner, student):
        q = _make_bank_question(client, owner)
        client.post(
            f"/api/bank/questions/{q['id']}/share",
            json={"usernames": ["student"]},
            headers=owner,
        )
        resp = client.post(f"/api/bank/questions/{q['id']}/fork", headers=student)
        assert resp.status_code == 201
        assert resp.json()["can_edit"] is True
        assert resp.json()["title"] == "你的年龄"


# ── 需求三：修改题目不影响已发布问卷 ──────────────────────────────────────────


class TestModificationIsolation:
    def test_modify_creates_new_version_and_keeps_old_survey(self, client, owner):
        q = _make_bank_question(client, owner)
        sid = _make_survey(client, owner, "问卷A")
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "x", "bank_question_id": q["id"]},
            headers=owner,
        )

        # 修改题库题目
        resp = client.put(
            f"/api/bank/questions/{q['id']}",
            json={"title": "您今年多大？", "options": ["18岁以下", "18-25岁"]},
            headers=owner,
        )
        assert resp.status_code == 200
        v2 = resp.json()
        assert v2["version"] == 2
        assert v2["title"] == "您今年多大？"
        assert v2["parent_id"] == q["id"]

        # 旧问卷里的题目保持原样
        qs = client.get(f"/api/surveys/{sid}/questions", headers=owner).json()
        assert qs[0]["title"] == "你的年龄"
        assert qs[0]["options"] == ["18岁以下", "18-25岁", "26岁以上"]
        assert qs[0]["bank_ref"]["version_id"] == q["id"]

    def test_published_survey_question_cannot_be_modified(self, client, owner):
        q = _make_bank_question(client, owner)
        sid = _make_survey(client, owner)
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "x", "bank_question_id": q["id"]},
            headers=owner,
        )
        client.post(f"/api/surveys/{sid}/publish", headers=owner)
        resp = client.put(
            f"/api/surveys/{sid}/questions/1",
            json={"title": "改一下"},
            headers=owner,
        )
        assert resp.status_code == 422


# ── 需求四 / 五：版本历史与版本共存 ───────────────────────────────────────────


class TestVersioning:
    def test_version_history_chain(self, client, owner):
        q = _make_bank_question(client, owner)
        v2 = client.put(
            f"/api/bank/questions/{q['id']}",
            json={"title": "v2 标题"},
            headers=owner,
        ).json()
        v3 = client.put(
            f"/api/bank/questions/{v2['id']}",
            json={"title": "v3 标题"},
            headers=owner,
        ).json()

        resp = client.get(f"/api/bank/questions/{q['id']}/versions", headers=owner)
        assert resp.status_code == 200
        versions = resp.json()["versions"]
        assert [v["version"] for v in versions] == [1, 2, 3]
        assert versions[0]["title"] == "你的年龄"
        assert versions[1]["parent_version"] == 1
        assert versions[2]["parent_version"] == 2
        assert versions[2]["is_latest"] is True

    def test_versions_coexist(self, client, owner):
        q = _make_bank_question(client, owner)
        v2 = client.put(
            f"/api/bank/questions/{q['id']}",
            json={"title": "v2 标题"},
            headers=owner,
        ).json()
        # v1 依然可读
        old = client.get(f"/api/bank/questions/{q['id']}", headers=owner).json()
        assert old["title"] == "你的年龄"
        assert old["version"] == 1
        assert old["is_latest"] is False

    def test_restore_old_version(self, client, owner):
        q = _make_bank_question(client, owner)
        v2 = client.put(
            f"/api/bank/questions/{q['id']}",
            json={"title": "v2 标题"},
            headers=owner,
        ).json()
        resp = client.post(
            f"/api/bank/questions/{v2['id']}/versions/{q['id']}/restore",
            headers=owner,
        )
        assert resp.status_code == 201
        restored = resp.json()
        assert restored["version"] == 3
        assert restored["title"] == "你的年龄"
        assert "恢复自 v1" in restored["note"]

    def test_two_surveys_use_different_versions(self, client, owner):
        q = _make_bank_question(client, owner)
        v2 = client.put(
            f"/api/bank/questions/{q['id']}",
            json={"title": "v2 标题"},
            headers=owner,
        ).json()

        sid_a = _make_survey(client, owner, "问卷A")
        client.post(
            f"/api/surveys/{sid_a}/questions",
            json={"type": "single", "title": "x", "bank_question_id": q["id"]},
            headers=owner,
        )
        sid_b = _make_survey(client, owner, "问卷B")
        client.post(
            f"/api/surveys/{sid_b}/questions",
            json={"type": "single", "title": "x", "bank_question_id": v2["id"]},
            headers=owner,
        )

        a = client.get(f"/api/surveys/{sid_a}/questions", headers=owner).json()[0]
        b = client.get(f"/api/surveys/{sid_b}/questions", headers=owner).json()[0]
        assert a["title"] == "你的年龄"
        assert b["title"] == "v2 标题"

    def test_switch_survey_question_to_new_version(self, client, owner):
        q = _make_bank_question(client, owner)
        v2 = client.put(
            f"/api/bank/questions/{q['id']}",
            json={"title": "v2 标题"},
            headers=owner,
        ).json()
        sid = _make_survey(client, owner)
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "x", "bank_question_id": q["id"]},
            headers=owner,
        )
        resp = client.put(
            f"/api/surveys/{sid}/questions/1",
            json={"bank_version_id": v2["id"]},
            headers=owner,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "v2 标题"
        assert resp.json()["bank_ref"]["version_id"] == v2["id"]


# ── 需求六：查看题目被哪些问卷使用 ───────────────────────────────────────────


class TestUsage:
    def test_usage_listing(self, client, owner):
        q = _make_bank_question(client, owner)
        sid1 = _make_survey(client, owner, "问卷A")
        sid2 = _make_survey(client, owner, "问卷B")
        for s in (sid1, sid2):
            client.post(
                f"/api/surveys/{s}/questions",
                json={"type": "single", "title": "x", "bank_question_id": q["id"]},
                headers=owner,
            )
        resp = client.get(f"/api/bank/questions/{q['id']}/usage", headers=owner)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert {i["survey_title"] for i in data["items"]} == {"问卷A", "问卷B"}
        assert all(i["is_current_version"] for i in data["items"])

    def test_usage_count_in_list(self, client, owner):
        q = _make_bank_question(client, owner)
        sid = _make_survey(client, owner)
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "x", "bank_question_id": q["id"]},
            headers=owner,
        )
        lst = client.get("/api/bank/questions", headers=owner).json()
        assert lst[0]["usage_count"] == 1

    def test_cannot_delete_used_question(self, client, owner):
        q = _make_bank_question(client, owner)
        sid = _make_survey(client, owner)
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "single", "title": "x", "bank_question_id": q["id"]},
            headers=owner,
        )
        resp = client.delete(f"/api/bank/questions/{q['id']}", headers=owner)
        assert resp.status_code == 422

    def test_delete_unused_question(self, client, owner):
        q = _make_bank_question(client, owner)
        resp = client.delete(f"/api/bank/questions/{q['id']}", headers=owner)
        assert resp.status_code == 204
        assert client.get(f"/api/bank/questions/{q['id']}", headers=owner).status_code == 404


# ── 需求七：题库管理 ──────────────────────────────────────────────────────────


class TestQuestionBank:
    def test_only_bank_listing(self, client, owner):
        _make_bank_question(client, owner, title="在题库里", in_bank=True)
        _make_bank_question(client, owner, title="不在题库里", in_bank=False)
        resp = client.get(
            "/api/bank/questions", params={"only_bank": "true"}, headers=owner
        )
        assert resp.status_code == 200
        titles = [x["title"] for x in resp.json()]
        assert titles == ["在题库里"]

    def test_toggle_bank_flag(self, client, owner):
        q = _make_bank_question(client, owner, in_bank=False)
        resp = client.post(
            f"/api/bank/questions/{q['id']}/bank",
            json={"in_bank": True},
            headers=owner,
        )
        assert resp.status_code == 200
        assert resp.json()["in_bank"] is True


# ── 需求八：跨问卷统计 ────────────────────────────────────────────────────────


class TestCrossSurveyStatistics:
    def _fill(self, client, headers, sid, value):
        client.post(f"/api/surveys/{sid}/publish", headers=headers)
        start = client.post(
            f"/api/surveys/{sid}/submit/start", headers=headers
        ).json()
        client.post(
            f"/api/surveys/{sid}/submit/{start['submission_id']}/answer",
            json={"question_order": 1, "value": value},
            headers=headers,
        )
        client.post(
            f"/api/surveys/{sid}/submit/{start['submission_id']}/finalize",
            headers=headers,
        )

    def test_cross_survey_stats(self, client, owner):
        q = _make_bank_question(client, owner)
        sid_a = _make_survey(client, owner, "问卷A")
        sid_b = _make_survey(client, owner, "问卷B")
        for s in (sid_a, sid_b):
            client.post(
                f"/api/surveys/{s}/questions",
                json={"type": "single", "title": "x", "bank_question_id": q["id"]},
                headers=owner,
            )
        self._fill(client, owner, sid_a, "18岁以下")
        self._fill(client, owner, sid_b, "18岁以下")
        self._fill(client, owner, sid_b, "26岁以上")

        resp = client.get(f"/api/bank/questions/{q['id']}/statistics", headers=owner)
        assert resp.status_code == 200
        data = resp.json()
        assert data["survey_count"] == 2
        assert data["total_answers"] == 3
        counts = {c["value"]: c["count"] for c in data["counts"]}
        assert counts == {"18岁以下": 2, "26岁以上": 1}
        assert len(data["by_survey"]) == 2
        assert sum(s["count"] for s in data["by_survey"]) == 3

    def test_number_question_stats(self, client, owner):
        q = _make_bank_question(
            client, owner, type="number", title="你的年龄", options=None
        )
        sid = _make_survey(client, owner, "问卷A")
        client.post(
            f"/api/surveys/{sid}/questions",
            json={"type": "number", "title": "x", "bank_question_id": q["id"]},
            headers=owner,
        )
        self._fill(client, owner, sid, 20)
        self._fill(client, owner, sid, 30)

        resp = client.get(f"/api/bank/questions/{q['id']}/statistics", headers=owner)
        data = resp.json()
        assert data["n"] == 2
        assert data["avg"] == 25
        assert data["min"] == 20
        assert data["max"] == 30

    def test_stats_requires_read_access(self, client, owner, student):
        q = _make_bank_question(client, owner)
        resp = client.get(f"/api/bank/questions/{q['id']}/statistics", headers=student)
        assert resp.status_code == 403
