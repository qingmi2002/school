"""T3.2 + T3.3 + V1.7 + V1.8 排课工作台、多方案切换、发布/锁定、空教室实时查询与全院总课表质量看板 API。"""
from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import get_optional_current_user
from app.core.week_mask import build_week_mask, masks_overlap, weeks_to_mask
from app.db.session import get_db
from app.models import (
    Classroom,
    PublicCourseLock,
    ScheduleDetail,
    SchedulePlan,
    Semester,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org.rbac import assert_org_subtree_access
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


@router.get("/free-rooms")
def query_free_rooms_api(
    week_no: int = Query(1, ge=1, le=30),
    day_of_week: int = Query(1, ge=1, le=7),
    period_index: int = Query(1, ge=1, le=6),
    semester_id: Optional[int] = Query(None),
    plan_id: Optional[int] = Query(None),
    room_type: Optional[str] = Query(None),
    building: Optional[str] = Query(None),
    min_capacity: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """V1.8 空教室实时查询：按第 X 周 + 星期 + 节次 + 类型 + 容量精准筛选空闲教室/机房。"""
    sem = (
        db.query(Semester).filter(Semester.id == semester_id).first()
        if semester_id
        else db.query(Semester).filter(Semester.is_current.is_(True)).first() or db.query(Semester).first()
    )
    target_mask = weeks_to_mask([week_no])
    ts_ids = {
        t.id
        for t in db.query(Timeslot)
        .filter(Timeslot.day_of_week == day_of_week, Timeslot.period_index == period_index)
        .all()
    }

    occupied_room_ids: set[int] = set()
    if sem is not None and ts_ids:
        plan = (
            db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
            if plan_id
            else db.query(SchedulePlan)
            .filter(SchedulePlan.semester_id == sem.id, SchedulePlan.is_published.is_(True))
            .order_by(SchedulePlan.id.desc())
            .first()
            or db.query(SchedulePlan)
            .filter(SchedulePlan.semester_id == sem.id)
            .order_by(SchedulePlan.id.desc())
            .first()
        )
        if plan is not None:
            details = (
                db.query(ScheduleDetail)
                .filter(ScheduleDetail.plan_id == plan.id, ScheduleDetail.timeslot_id.in_(ts_ids))
                .all()
            )
            task_map = {t.id: t for t in db.query(TeachingTask).filter(TeachingTask.semester_id == sem.id).all()}
            for d in details:
                t = task_map.get(d.task_id)
                dm = (
                    d.week_mask
                    or (t.week_mask if t else None)
                    or build_week_mask(t.start_week if t else 1, t.end_week if t else 18, d.week_type)
                )
                if masks_overlap(dm, target_mask):
                    occupied_room_ids.add(d.classroom_id)

        locks = (
            db.query(PublicCourseLock)
            .filter(PublicCourseLock.semester_id == sem.id, PublicCourseLock.timeslot_id.in_(ts_ids))
            .all()
        )
        for lk in locks:
            if lk.classroom_id and masks_overlap(build_week_mask(1, 30, lk.week_type), target_mask):
                occupied_room_ids.add(lk.classroom_id)

    rooms = db.query(Classroom).filter(Classroom.is_active.is_(True)).order_by(Classroom.building, Classroom.room_code).all()
    cohort_map = {c.id: c.cohort_name for c in db.query(StudentCohort).all()}
    free_rooms = []
    for r in rooms:
        if r.id in occupied_room_ids:
            continue
        if room_type and r.room_type != room_type:
            continue
        if building and building not in r.building:
            continue
        if r.capacity < min_capacity:
            continue
        free_rooms.append(
            {
                "id": r.id,
                "room_code": r.room_code,
                "building": r.building,
                "capacity": r.capacity,
                "room_type": r.room_type,
                "usage_mode": r.usage_mode,
                "fixed_cohort_name": cohort_map.get(r.fixed_cohort_id) if r.fixed_cohort_id else None,
                "sharing_policy": r.sharing_policy,
            }
        )
    return {
        "week_no": week_no,
        "day_of_week": day_of_week,
        "period_index": period_index,
        "total_rooms": len(rooms),
        "occupied_count": len(occupied_room_ids),
        "free_count": len(free_rooms),
        "free_rooms": free_rooms,
    }


@router.get("/plans/{plan_id}/analytics")
def get_plan_analytics_and_master_matrix(plan_id: int, db: Session = Depends(get_db)):
    """V1.8 排课质量看板与全院二维总课表（班级 × 周一至周五节次）。"""
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="排课方案不存在")

    details = db.query(ScheduleDetail).filter(ScheduleDetail.plan_id == plan_id).all()
    tasks = db.query(TeachingTask).filter(TeachingTask.semester_id == plan.semester_id).all()
    task_map = {t.id: t for t in tasks}
    ts_list = db.query(Timeslot).all()
    ts_map = {t.id: t for t in ts_list}
    rooms = db.query(Classroom).filter(Classroom.is_active.is_(True)).all()
    room_map = {r.id: r for r in rooms}
    user_map = {u.id: u.real_name for u in db.query(SysUser).all()}
    cohorts = db.query(StudentCohort).order_by(StudentCohort.cohort_code).all()

    total_required_sessions = sum(int(t.weekly_sessions or 0) for t in tasks)
    scheduled_sessions = len(details)
    completion_rate = round((scheduled_sessions / max(total_required_sessions, 1)) * 100.0, 1)

    room_used_counts: dict[int, int] = defaultdict(int)
    evening_count = 0
    combined_count = 0
    manual_count = 0
    cohort_grid: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for d in details:
        room_used_counts[d.classroom_id] += 1
        if d.is_manual_adjusted:
            manual_count += 1
        ts = ts_map.get(d.timeslot_id)
        t = task_map.get(d.task_id)
        rm = room_map.get(d.classroom_id)
        if ts and ts.is_evening:
            evening_count += 1
        if t and len(t.cohort_ids or []) >= 2:
            combined_count += 1
        if ts and t:
            slot_key = f"{ts.day_of_week}-{ts.period_index}"
            tname = user_map.get(t.teacher_id, "")
            rcode = rm.room_code if rm else ""
            label = f"{t.course_name}({tname}@{rcode})"
            for cid in t.cohort_ids or []:
                cohort_grid[cid][slot_key].append(label)

    total_slots = max(len(ts_list), 25)
    room_utilization = []
    for r in rooms:
        used = room_used_counts.get(r.id, 0)
        room_utilization.append(
            {
                "room_id": r.id,
                "room_code": r.room_code,
                "building": r.building,
                "room_type": r.room_type,
                "used_slots": used,
                "utilization_pct": round((used / total_slots) * 100.0, 1),
            }
        )
    room_utilization.sort(key=lambda x: (-x["utilization_pct"], x["room_code"]))
    avg_util = round(sum(x["utilization_pct"] for x in room_utilization) / max(len(room_utilization), 1), 1)

    master_matrix = [
        {
            "cohort_id": c.id,
            "cohort_name": c.cohort_name,
            "student_count": c.student_count,
            "slots": {k: " / ".join(v) for k, v in cohort_grid.get(c.id, {}).items()},
        }
        for c in cohorts
    ]

    return {
        "plan_id": plan.id,
        "plan_name": plan.plan_name,
        "is_published": bool(plan.is_published),
        "total_tasks": len(tasks),
        "scheduled_sessions": scheduled_sessions,
        "completion_rate": min(completion_rate, 100.0),
        "avg_room_utilization": avg_util,
        "evening_sessions_count": evening_count,
        "combined_sessions_count": combined_count,
        "manual_adjusted_count": manual_count,
        "room_utilization": room_utilization,
        "master_matrix": master_matrix,
    }


@router.get("/plans")
def list_schedule_plans_api(
    semester_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
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
def publish_schedule_plan_api(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="排课方案不存在")
    assert_org_subtree_access(db, current_user, plan.org_node_id)
    db.query(SchedulePlan).filter(
        SchedulePlan.semester_id == plan.semester_id,
        SchedulePlan.org_node_id == plan.org_node_id,
        SchedulePlan.id != plan.id,
    ).update({"is_published": False})
    plan.is_published = True
    db.commit()
    return {"published": True, "plan_id": plan.id, "plan_name": plan.plan_name}


@router.patch("/tasks/{task_id}/lock")
def toggle_task_lock_api(
    task_id: int,
    payload: TaskLockIn,
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    task = db.query(TeachingTask).filter(TeachingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="教学任务不存在")
    assert_org_subtree_access(db, current_user, task.org_node_id)
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
