"""FastAPI application factory.

Route handlers only orchestrate calls into `app.services.*`, which in
turn call the unmodified Phase 2/3 domain logic
(`app.reconciliation`, `app.auto_resolution`, `app.review`). No
business logic lives in this module or in `app.api.routers.*`.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import ai, dashboard, datasets, evaluation, exceptions, health, reconciliation, review

# Local dev origins only (Vite's default port plus a couple of common
# alternates). No auth exists yet (intentionally, per project scope),
# so this is never widened to "*".
_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _allowed_origins() -> list[str]:
    """Deployed frontend origin(s), configured via CORS_ALLOWED_ORIGINS
    (comma-separated). Falls back to the local Vite dev origins when
    unset, so local development is unaffected. See docs/deployment.md.
    """
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins if origins else _DEV_ORIGINS


def create_app() -> FastAPI:
    app = FastAPI(title="RazorRecon AI", version="0.4.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(datasets.router)
    app.include_router(reconciliation.router)
    app.include_router(exceptions.router)
    app.include_router(review.router)
    app.include_router(dashboard.router)
    app.include_router(ai.router)
    app.include_router(evaluation.router)

    return app


app = create_app()
