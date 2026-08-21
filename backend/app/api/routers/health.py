from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.schemas import HealthResponse
from app.db.base import get_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception:  # noqa: BLE001 - health check must never raise
        database_status = "unavailable"
    return HealthResponse(status="ok", database=database_status)
