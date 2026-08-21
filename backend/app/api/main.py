"""FastAPI application factory.

Route handlers only orchestrate calls into `app.services.*`, which in
turn call the unmodified Phase 2/3 domain logic
(`app.reconciliation`, `app.auto_resolution`, `app.review`). No
business logic lives in this module or in `app.api.routers.*`.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import ai, dashboard, datasets, exceptions, health, reconciliation, review

# Local dev origins only (Vite's default port plus a couple of common
# alternates). No auth exists yet (intentionally, per project scope),
# so this is not widened to "*" or to any non-local origin.
_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_app() -> FastAPI:
    app = FastAPI(title="RazorRecon AI", version="0.4.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
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

    return app


app = create_app()
