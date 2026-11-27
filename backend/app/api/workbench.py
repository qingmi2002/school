"""T3.2 + T3.3 + V1.7 排课工作台三重视角、多方案切换、正式发布、单课锁定与调停课审批 REST API。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import SchedulePlan, TeachingTask
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


class TaskLockIn(BaseModel):
    is_locked: bool


@router.get("/plans")
def list_schedule_plans_api(
    semester_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """V1.7 列出历史排课方案（供工作台切换对比与发布）。"""
    q = db.query(SchedulePlan)
    if semester_id is not None:
        q = q.filter(SchedulePlan.semester_id == semester_id)
    rows = q.order_by(SchedulePlan.id.desc()).all()
    return [
        {
            "id": p.id,
            "semester_id": p.semester_id,
            "org_node_id": p.org_node_id,
            "plan_name": p.plan_name,
            "version_tag": p.version_tag,
            "run_mode": p.run_mode,
            "fitness_score": float(p.fitness_score or 0),
            "is_published": bool(p.is_published),
        }
        for p in rows
    ]


@router.post("/plans/{plan_id}/publish")
def publish_schedule_plan_api(plan_id: int, db: Session = Depends(get_db)):
    """V1.7 正式发布排课方案（同组织同学期其他方案自动置为未发布，师生端立即可见）。"""
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="排课方案不存在")
    db.query(SchedulePlan).filter(
        SchedulePlan.semester_id == plan.semester_id,
        SchedulePlan.org_node_id == plan.org_node_id,
        SchedulePlan.id != plan.id,
    ).update({"is_published": False})
    plan.is_published = True
    db.commit()
    return {"published": True, "plan_id": plan.id, "plan_name": plan.plan_name}


@router.patch("/tasks/{task_id}/lock")
def toggle_task_lock_api(task_id: int, payload: TaskLockIn, db: Session = Depends(get_db)):
    """V1.7 锁定或解锁单门教学任务（锁定后一键重排将自动占坑避让，不覆盖该课）。"""
    task = db.query(TeachingTask).filter(TeachingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="教学任务不存在")
    task.is_locked = payload.is_locked
    db.commit()
    return {"task_id": task.id, "is_locked": task.is_locked}


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
