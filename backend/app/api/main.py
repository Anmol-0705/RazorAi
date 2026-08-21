"""FastAPI application factory.

Route handlers only orchestrate calls into `app.services.*`, which in
turn call the unmodified Phase 2/3 domain logic
(`app.reconciliation`, `app.auto_resolution`, `app.review`). No
business logic lives in this module or in `app.api.routers.*`.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routers import dashboard, datasets, exceptions, health, reconciliation, review


def create_app() -> FastAPI:
    app = FastAPI(title="RazorRecon AI", version="0.4.0")

    app.include_router(health.router)
    app.include_router(datasets.router)
    app.include_router(reconciliation.router)
    app.include_router(exceptions.router)
    app.include_router(review.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
