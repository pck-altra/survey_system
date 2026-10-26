"""Pytest fixtures shared by all test modules."""
from __future__ import annotations

import pytest
from bson import ObjectId

from app import get_db, reset_client, ensure_indexes
from app.config import config


# Reduce connection pool size for tests to avoid "Too many open files" on
# resource-constrained MongoDB instances (e.g. local laptop install).
_original_timeout = config.MONGO_TIMEOUT_MS
config.MONGO_TIMEOUT_MS = 10000


# 整个测试会话共用一个测试库。
#
# 背景：本机 mongod 由 launchd 托管，文件描述符上限只有 256。如果每个用例
# 都新建一个数据库，集合与索引文件会在服务端不断累积（每个库约 20 个文件），
# 几十个用例之后就会触发 "Too many open files"。因此这里按 **会话** 复用一个
# 库，用例之间只清空数据，既保证用例隔离，又不会撑爆文件描述符。
COLLECTIONS = [
    "answers",
    "responses",
    "questions",
    "surveys",
    "users",
    "bank_questions",
]


def clean_collections(db) -> None:
    """清空所有集合，保证用例之间互不干扰。"""
    for coll in COLLECTIONS:
        try:
            db[coll].delete_many({})
        except Exception:
            pass


@pytest.fixture(scope="session")
def session_db():
    """会话级测试数据库。

    * 把 ``config.MONGO_DB`` 指向临时库，FastAPI 的 ``get_db()``（以及
      ``TestClient`` 启动时的 ``ensure_indexes``）都会落到这个库上，
      不会污染正式的 ``survey_system`` 库。
    * 会话结束时整体 drop 掉。
    """
    original_db = config.MONGO_DB
    test_db = f"survey_system_test_{ObjectId()}"

    reset_client()
    config.MONGO_DB = test_db

    db = get_db()
    ensure_indexes(db)

    yield db

    # teardown — drop the whole database
    try:
        db.client.drop_database(test_db)
    except Exception:
        pass  # ignore if MongoDB is temporarily unreachable

    config.MONGO_DB = original_db
    reset_client()


@pytest.fixture(scope="function")
def db(session_db):
    """返回会话级测试数据库，使用前先清空数据。"""
    clean_collections(session_db)
    return session_db
