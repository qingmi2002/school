"""T2.2 分级公共课基线锁定与自由下发 REST API。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.locks.schemas import (
    BaselineLockBatchCreate,
    EffectiveBaselineLocksOut,
    PublishPlanAsBaselineRequest,
)
from app.locks.service import (
    delete_baseline_lock,
    get_effective_locks_for_node,
    publish_plan_as_baseline,
    upsert_baseline_locks,
)

router = APIRouter(prefix="/locks", tags=["baseline-locks"])


@router.post("/batch")
def batch_upsert_locks_api(payload: BaselineLockBatchCreate, db: Session = Depends(get_db)):
    try:
        rows = upsert_baseline_locks(db, payload)
        return {"lock_scope_org_id": payload.lock_scope_org_id, "created_count": len(rows)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/publish-from-plan")
def publish_plan_as_baseline_api(
    payload: PublishPlanAsBaselineRequest, db: Session = Depends(get_db)
):
    try:
        rows = publish_plan_as_baseline(
            db=db,
            plan_id=payload.plan_id,
            lock_scope_org_id=payload.lock_scope_org_id,
            replace_existing=payload.replace_existing,
        )
        return {"plan_id": payload.plan_id, "locked_count": len(rows)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/effective/{org_node_id}", response_model=EffectiveBaselineLocksOut)
def get_effective_locks_api(
    org_node_id: int,
    semester_id: int = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return get_effective_locks_for_node(db, semester_id=semester_id, target_org_node_id=org_node_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{lock_id}")
def delete_lock_api(
    lock_id: int,
    operator_org_node_id: int = Query(...),
    db: Session = Depends(get_db),
):
    try:
        delete_baseline_lock(db, lock_id=lock_id, operator_org_node_id=operator_org_node_id)
        return {"deleted_lock_id": lock_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
