from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import ReviewActionRequest, ReviewActionResponse
from app.db.base import get_db
from app.services import review_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/exceptions", tags=["review"])

_ACTION_ROUTES = ("start-review", "approve", "reject", "mark-resolved", "add-note")


def _do_action(action: str, exception_id: str, request: ReviewActionRequest, db: Session):
    try:
        row, audit = review_service.apply_review_action(
            db,
            exception_id=exception_id,
            action=action.replace("-", "_"),
            reviewer=request.reviewer,
            note=request.note,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReviewActionResponse(exception=row, audit=audit)


@router.post("/{exception_id}/start-review", response_model=ReviewActionResponse)
def start_review(exception_id: str, request: ReviewActionRequest, db: Session = Depends(get_db)):
    return _do_action("start-review", exception_id, request, db)


@router.post("/{exception_id}/approve", response_model=ReviewActionResponse)
def approve(exception_id: str, request: ReviewActionRequest, db: Session = Depends(get_db)):
    return _do_action("approve", exception_id, request, db)


@router.post("/{exception_id}/reject", response_model=ReviewActionResponse)
def reject(exception_id: str, request: ReviewActionRequest, db: Session = Depends(get_db)):
    return _do_action("reject", exception_id, request, db)


@router.post("/{exception_id}/mark-resolved", response_model=ReviewActionResponse)
def mark_resolved(exception_id: str, request: ReviewActionRequest, db: Session = Depends(get_db)):
    return _do_action("mark-resolved", exception_id, request, db)


@router.post("/{exception_id}/add-note", response_model=ReviewActionResponse)
def add_note(exception_id: str, request: ReviewActionRequest, db: Session = Depends(get_db)):
    return _do_action("add-note", exception_id, request, db)
