from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import DashboardSummaryResponse
from app.db.base import get_db
from app.services import dashboard_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_summary(run_id: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    try:
        return dashboard_service.compute_summary(db, run_id=run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
