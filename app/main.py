"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import ensure_indexes, get_db
from .config import config

app = FastAPI(
    title="Survey System API",
    description="Simplified online survey system based on MongoDB",
    version="1.0.0",
)

# Allow static frontend to call the API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Create MongoDB indexes on startup (idempotent)."""
    db = get_db()
    ensure_indexes(db)


# ── mount sub-routers ────────────────────────────────────────────────────────
from .api import auth, surveys, questions, responses, statistics

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(surveys.router, prefix="/api/surveys", tags=["surveys"])
app.include_router(questions.router, prefix="/api/surveys", tags=["questions"])
app.include_router(responses.router, prefix="/api/surveys", tags=["responses"])
app.include_router(statistics.router, prefix="/api/surveys", tags=["statistics"])


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "db": config.MONGO_DB}
