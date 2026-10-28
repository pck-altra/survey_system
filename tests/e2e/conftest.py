"""端到端（E2E）测试夹具。

与 ``tests/conftest.py``（单元 / 接口级）不同，本目录的用例**不使用**
FastAPI ``TestClient``，而是：

1. 真的拉起一个 ``uvicorn`` 子进程（真实的 ASGI 服务器、真实的中间件栈）；
2. 指向一个**独立的临时 MongoDB 库**（``survey_system_e2e_<随机>``），
   绝不污染开发库 ``survey_system``；
3. 通过 **HTTP**（httpx）驱动整个业务流程，验证的是"用户真正做的事"
   ——注册 → 建卷 → 加题 → 发布 → 填写 → 统计。

这样能覆盖单元测试覆盖不到的部分：中间件 / 路由重定向 / 真实序列化 /
真实数据库写入 / 真实状态机流转。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Iterator

import httpx
import pytest
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]

COLLECTIONS = [
    "answers",
    "responses",
    "questions",
    "surveys",
    "users",
    "bank_questions",
]


# ── helpers ──────────────────────────────────────────────────────────────────


def free_port() -> int:
    """申请一个当前空闲的本地端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class E2EServer:
    """一个跑在子进程里的真实 uvicorn 服务。"""

    def __init__(self, proc: subprocess.Popen, port: int, db_name: str):
        self.proc = proc
        self.port = port
        self.db_name = db_name
        self.base_url = f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


@pytest.fixture(scope="session")
def e2e_server() -> Iterator[E2EServer]:
    """会话级：启动一个真实的后端服务，指向独立的临时数据库。"""
    port = int(os.environ.get("E2E_API_PORT") or free_port())
    db_name = f"survey_system_e2e_{uuid.uuid4().hex[:8]}"

    env = os.environ.copy()
    env["SURVEY_MONGO_DB"] = db_name
    # 测试环境降低 bcrypt 代价，加快端到端用例的执行速度
    env.setdefault("SURVEY_BCRYPT_COST", "4")
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    server = E2EServer(proc, port, db_name)

    # 等待服务就绪
    deadline = time.time() + 45
    last_error: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            pytest.fail(f"后端进程启动失败（退出码 {proc.returncode}）：\n{output}")
        try:
            resp = httpx.get(f"{server.base_url}/api/health", timeout=2.0)
            if resp.status_code == 200:
                break
        except Exception as exc:  # noqa: BLE001 - 启动期间连接失败属正常
            last_error = exc
        time.sleep(0.25)
    else:
        server.stop()
        pytest.fail(f"后端在 45 秒内未就绪：{last_error}")

    yield server

    server.stop()
    # 清理临时库
    try:
        cli = MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=3000)
        cli.drop_database(db_name)
        cli.close()
    except Exception:  # noqa: BLE001 - 清理失败不应影响测试结论
        pass


@pytest.fixture(scope="session")
def e2e_base_url(e2e_server: E2EServer) -> str:
    return e2e_server.base_url


@pytest.fixture()
def e2e_client(e2e_base_url: str) -> Iterator[httpx.Client]:
    """函数级 HTTP 客户端（跟随重定向，处理 ``/api/surveys`` → ``/api/surveys/``）。"""
    with httpx.Client(
        base_url=e2e_base_url,
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        yield client


@pytest.fixture()
def e2e_db(e2e_server: E2EServer) -> Iterator[object]:
    """函数级：每个用例开始前清空集合，保证用例之间互不干扰。"""
    cli = MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=5000)
    db = cli[e2e_server.db_name]
    for coll in COLLECTIONS:
        db[coll].delete_many({})
    try:
        yield db
    finally:
        cli.close()


# ── 高层操作封装（供用例直接调用）────────────────────────────────────────────


def register(client: httpx.Client, username: str, password: str = "pass1234") -> dict:
    """注册并返回用户信息（201）。"""
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def login(client: httpx.Client, username: str, password: str = "pass1234") -> str:
    """登录并返回 access token。"""
    resp = client.post(
        "/api/auth/login",
        params={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    """构造 Authorization 头。"""
    return {"Authorization": f"Bearer {token}"}


def create_survey(
    client: httpx.Client,
    token: str,
    title: str = "E2E 测试问卷",
    description: str = "",
    allow_anonymous: bool = False,
) -> dict:
    """创建问卷（201）。"""
    resp = client.post(
        "/api/surveys/",
        json={
            "title": title,
            "description": description,
            "allow_anonymous": allow_anonymous,
        },
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_question(
    client: httpx.Client,
    token: str,
    survey_id: str,
    *,
    qtype: str = "text",
    title: str = "题目",
    options: list[str] | None = None,
    required: bool = False,
    validation: dict | None = None,
    next_rule: dict | None = None,
    bank_question_id: str | None = None,
) -> dict:
    """添加题目（201）。"""
    body: dict = {
        "type": qtype,
        "title": title,
        "options": options,
        "required": required,
        "validation": validation or {},
        "next_rule": next_rule or {"mode": "default", "fallback": "next"},
    }
    if bank_question_id is not None:
        body["bank_question_id"] = bank_question_id
        body.pop("type")
        body.pop("title")
    resp = client.post(
        f"/api/surveys/{survey_id}/questions",
        json=body,
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def publish(client: httpx.Client, token: str, survey_id: str) -> dict:
    """发布问卷，返回含 token 的问卷对象。"""
    resp = client.post(f"/api/surveys/{survey_id}/publish", headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def start_submission(client: httpx.Client, token: str, survey_id: str) -> dict:
    """开始填写问卷。"""
    resp = client.post(f"/api/surveys/{survey_id}/submit/start", headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def answer(
    client: httpx.Client,
    token: str,
    survey_id: str,
    submission_id: str,
    question_order: int,
    value,
) -> dict:
    """提交一道题的答案，返回下一题信息。"""
    resp = client.post(
        f"/api/surveys/{survey_id}/submit/{submission_id}/answer",
        json={"question_order": question_order, "value": value},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def finalize(client: httpx.Client, token: str, survey_id: str, submission_id: str) -> dict:
    """完成提交。"""
    resp = client.post(
        f"/api/surveys/{survey_id}/submit/{submission_id}/finalize",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def fill_survey(
    client: httpx.Client,
    token: str,
    survey_id: str,
    answers: list[tuple[int, object]],
) -> str:
    """按给定顺序完成一次完整填写，返回 submission_id。"""
    start = start_submission(client, token, survey_id)
    sid = start["submission_id"]
    for order, value in answers:
        answer(client, token, survey_id, sid, order, value)
    finalize(client, token, survey_id, sid)
    return sid
