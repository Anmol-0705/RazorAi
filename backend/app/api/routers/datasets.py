from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.schemas import GenerateDatasetRequest, GenerateDatasetResponse
from app.db.base import get_db
from app.services.dataset_service import generate_and_persist_demo_dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/demo", response_model=GenerateDatasetResponse)
def create_demo_dataset(
    request: GenerateDatasetRequest, response: Response, db: Session = Depends(get_db)
) -> GenerateDatasetResponse:
    result = generate_and_persist_demo_dataset(db, seed=request.seed, num_records=request.num_records)
    response.status_code = 201 if result["created"] else 200
    return GenerateDatasetResponse(**result)
