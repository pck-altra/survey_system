"""survey_system database layer.

Public entry points:

* :func:`get_db` / :func:`get_client` — Mongo handles
* :func:`ensure_indexes` — apply schema indexes
* ``app.models`` — repository functions for each collection
"""

from .db import ensure_indexes, get_client, get_db, reset_client  # noqa: F401
