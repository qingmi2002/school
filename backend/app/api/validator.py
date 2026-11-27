"""T3.1 毫秒级红绿灯拖拽校验与全校/院系一键体检 REST API。"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.validator.conflict_engine import execute_smart_swap
from app.validator.conflict_engine import (
    apply_drag_move,
    check_drag_target,
    compute_matrix_lights,
    run_health_check,
)
from app.validator.schemas import (
    DragCheckRequest,
    HealthCheckReport,
    MatrixLightsRequest,
    MatrixLightsResponse,
    SlotLightResult,
)

router = APIRouter(prefix="/validator", tags=["validator"])


@router.post("/drag-check", response_model=SlotLightResult)
def drag_check_api(req: DragCheckRequest, db: Session = Depends(get_db)):
    try:
        return check_drag_target(db, req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/matrix-lights", response_model=MatrixLightsResponse)
def matrix_lights_api(req: MatrixLightsRequest, db: Session = Depends(get_db)):
    try:
        return compute_matrix_lights(db, req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/drag-apply", response_model=SlotLightResult)
def drag_apply_api(req: DragCheckRequest, db: Session = Depends(get_db)):
    try:
        res = apply_drag_move(db, req)
        if not res.allowed:
            raise HTTPException(status_code=409, detail=res.model_dump())
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/health-check", response_model=HealthCheckReport)
def health_check_api(
    semester_id: int = Query(...),
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = Query("SCHOOL_WIDE"),
    org_node_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    return run_health_check(db, semester_id=semester_id, scope=scope, org_node_id=org_node_id)


class SmartSwapIn(BaseModel):
    plan_id: int
    detail_id_a: int
    detail_id_b: int
    scope: str = "SINGLE_DEPT"


@router.post("/swap")
def smart_swap_api(payload: SmartSwapIn, db: Session = Depends(get_db)):
    """V1.8 拖拽智能对调接口：检测双方零冲突后一键互换两门课的时间片与教室。"""
    try:
        return execute_smart_swap(
            db,
            plan_id=payload.plan_id,
            detail_id_a=payload.detail_id_a,
            detail_id_b=payload.detail_id_b,
            scope=payload.scope,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
