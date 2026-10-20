#!/usr/bin/env python
"""Ensure all MongoDB indexes exist in the ``survey_system`` database.

Intended to be run once on deployment::

    python -m app.scripts.ensure_indexes

Idempotent — safe to call repeatedly.
"""
from __future__ import annotations

import sys
from pathlib import Path

# add project root to path so this can be run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ensure_indexes, get_db
from app.config import config


def main() -> None:
    db = get_db()
    print(f"[ensure_indexes] applying indexes to database '{config.MONGO_DB}' ...")
    ensure_indexes(db)
    print("[ensure_indexes] done.")


if __name__ == "__main__":
    main()
