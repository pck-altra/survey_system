"""REST API layer.

All routers are imported and mounted in ``app.main``.
"""
from . import auth, questions, responses, statistics, surveys  # noqa: F401
