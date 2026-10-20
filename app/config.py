# MongoDB connection configuration for the survey system.
# Override via environment variables for tests / different deployments.
from __future__ import annotations

import os


class Config:
    """Runtime configuration.

    All values are read from environment variables so the same code path
    can target development, tests, and production without modification.
    """

    # MongoDB connection URI.
    # Default targets the locally installed mongod (per project spec).
    MONGO_URI: str = os.environ.get(
        "SURVEY_MONGO_URI",
        "mongodb://127.0.0.1:27017",
    )

    # Logical database name inside the cluster.
    MONGO_DB: str = os.environ.get("SURVEY_MONGO_DB", "survey_system")

    # bcrypt cost factor — keep in sync with docs/数据库设计.md §4.1.
    BCRYPT_COST: int = int(os.environ.get("SURVEY_BCRYPT_COST", "12"))

    # Token length for published surveys (also documented in 设计文档 §4.2).
    SURVEY_TOKEN_LEN: int = int(os.environ.get("SURVEY_TOKEN_LEN", "7"))

    # Default request timeout in milliseconds for Mongo operations.
    MONGO_TIMEOUT_MS: int = int(os.environ.get("SURVEY_MONGO_TIMEOUT_MS", "5000"))


config = Config()
