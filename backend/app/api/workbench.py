"""T3.2 + T3.3 排课工作台三重视角与调停课审批 REST API。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.workbench.schemas import (
    ChangeRequestCreate,
    ChangeRequestOut,
    ChangeRequestReview,
    WorkbenchViewOut,
)
from app.workbench.service import (
    create_change_request,
    get_workbench_view,
    list_change_requests,
    review_change_request,
)

router = APIRouter(prefix="/workbench", tags=["workbench"])


@router.get("/plans/{plan_id}", response_model=WorkbenchViewOut)
def get_workbench_view_api(plan_id: int, db: Session = Depends(get_db)):
    try:
        return get_workbench_view(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plans/{plan_id}/change-requests", response_model=List[ChangeRequestOut])
def list_change_requests_api(plan_id: int, db: Session = Depends(get_db)):
    return list_change_requests(db, plan_id)


@router.post("/change-requests", response_model=ChangeRequestOut)
def create_change_request_api(payload: ChangeRequestCreate, db: Session = Depends(get_db)):
    return create_change_request(db, payload)


@router.post("/change-requests/{audit_id}/review", response_model=ChangeRequestOut)
def review_change_request_api(
    audit_id: int, payload: ChangeRequestReview, db: Session = Depends(get_db)
):
    try:
        return review_change_request(db, audit_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
