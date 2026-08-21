from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import ExceptionCaseResponse, ExceptionDetailResponse
from app.db.base import get_db
from app.services import exception_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("", response_model=list[ExceptionCaseResponse])
def get_exceptions(
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    exception_type: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, gt=0, le=1000),
    db: Session = Depends(get_db),
):
    return exception_service.list_exceptions(
        db, status=status, severity=severity, exception_type=exception_type, run_id=run_id, limit=limit
    )


@router.get("/{exception_id}", response_model=ExceptionDetailResponse)
def get_exception(exception_id: str, db: Session = Depends(get_db)) -> ExceptionDetailResponse:
    try:
        detail = exception_service.get_exception_detail(db, exception_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExceptionDetailResponse(
        exception=detail["exception"],
        result=detail["result"],
        auto_resolutions=detail["auto_resolutions"],
        review_audits=detail["review_audits"],
    )
