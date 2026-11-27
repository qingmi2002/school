"""V1.4 + V1.9 班级周历进程表（整周实训/实习/考试/停课）与周次位掩码联动重算 REST API。"""
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import get_optional_current_user
from app.core.week_mask import (
    build_week_mask,
    fit_week_mask_to_hours,
    mask_to_label,
    subtract_blocked_weeks,
    weeks_to_mask,
)
from app.db.session import get_db
from app.models import Classroom, CohortWeekPlan, Semester, StudentCohort, SysUser, TeachingTask
from app.org.rbac import assert_org_subtree_access

router = APIRouter(prefix="/week-plan", tags=["week-plan"])


class WeekCellOut(BaseModel):
    week_no: int
    week_mode: str
    block_course_name: Optional[str] = None
    block_teacher_id: Optional[int] = None
    block_classroom_id: Optional[int] = None
    remark: Optional[str] = None


class CohortWeekRowOut(BaseModel):
    cohort_id: int
    cohort_code: str
    cohort_name: str
    blocked_mask: int
    effective_regular_label: str
    cells: Dict[int, WeekCellOut]


class WeekPlanMatrixOut(BaseModel):
    semester_id: int
    total_weeks: int
    rows: List[CohortWeekRowOut]


class WeekRangeUpsert(BaseModel):
    semester_id: int
    cohort_id: int
    start_week: int
    end_week: int
    week_mode: Literal["REGULAR", "PRACTICUM", "INTERNSHIP", "EXAM", "HOLIDAY"]
    block_course_name: Optional[str] = None
    block_teacher_id: Optional[int] = None
    block_classroom_id: Optional[int] = None
    remark: Optional[str] = None


def get_cohort_blocked_mask(db: Session, semester_id: int, cohort_ids: List[int]) -> int:
    if not cohort_ids:
        return 0
    rows = (
        db.query(CohortWeekPlan)
        .filter(
            CohortWeekPlan.semester_id == semester_id,
            CohortWeekPlan.cohort_id.in_(cohort_ids),
            CohortWeekPlan.week_mode != "REGULAR",
        )
        .all()
    )
    return weeks_to_mask(r.week_no for r in rows)


@router.get("/matrix", response_model=WeekPlanMatrixOut)
def get_week_plan_matrix(semester_id: int = Query(1), db: Session = Depends(get_db)):
    sem = db.query(Semester).filter(Semester.id == semester_id).first()
    total_weeks = sem.total_weeks if sem else 18

    cohorts = db.query(StudentCohort).order_by(StudentCohort.id).all()
    plans = db.query(CohortWeekPlan).filter(CohortWeekPlan.semester_id == semester_id).all()
    by_cohort: Dict[int, Dict[int, CohortWeekPlan]] = {}
    for p in plans:
        by_cohort.setdefault(p.cohort_id, {})[p.week_no] = p

    full_mask = build_week_mask(1, total_weeks, 0)
    rows_out: List[CohortWeekRowOut] = []
    for c in cohorts:
        c_plans = by_cohort.get(c.id, {})
        blocked_weeks = [w for w, rec in c_plans.items() if rec.week_mode != "REGULAR"]
        b_mask = weeks_to_mask(blocked_weeks)
        eff_mask = subtract_blocked_weeks(full_mask, b_mask)
        cells: Dict[int, WeekCellOut] = {}
        for w in range(1, total_weeks + 1):
            rec = c_plans.get(w)
            cells[w] = WeekCellOut(
                week_no=w,
                week_mode=rec.week_mode if rec else "REGULAR",
                block_course_name=rec.block_course_name if rec else None,
                block_teacher_id=rec.block_teacher_id if rec else None,
                block_classroom_id=rec.block_classroom_id if rec else None,
                remark=rec.remark if rec else None,
            )
        rows_out.append(
            CohortWeekRowOut(
                cohort_id=c.id,
                cohort_code=c.cohort_code,
                cohort_name=c.cohort_name,
                blocked_mask=b_mask,
                effective_regular_label=mask_to_label(eff_mask),
                cells=cells,
            )
        )

    return WeekPlanMatrixOut(semester_id=semester_id, total_weeks=total_weeks, rows=rows_out)


@router.put("/range")
def upsert_week_range(
    payload: WeekRangeUpsert,
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    if payload.start_week > payload.end_week or payload.start_week < 1 or payload.end_week > 30:
        raise HTTPException(status_code=400, detail="周次范围非法（需在 1..30 之间且起始周不大于结束周）")

    for w in range(payload.start_week, payload.end_week + 1):
        rec = (
            db.query(CohortWeekPlan)
            .filter(
                CohortWeekPlan.semester_id == payload.semester_id,
                CohortWeekPlan.cohort_id == payload.cohort_id,
                CohortWeekPlan.week_no == w,
            )
            .first()
        )
        if payload.week_mode == "REGULAR":
            if rec:
                db.delete(rec)
        else:
            if rec is None:
                rec = CohortWeekPlan(
                    semester_id=payload.semester_id,
                    cohort_id=payload.cohort_id,
                    week_no=w,
                )
                db.add(rec)
            rec.week_mode = payload.week_mode
            rec.block_course_name = payload.block_course_name
            rec.block_teacher_id = payload.block_teacher_id
            rec.block_classroom_id = payload.block_classroom_id
            rec.remark = payload.remark

    cohort_row = db.query(StudentCohort).filter(StudentCohort.id == payload.cohort_id).first()
    if cohort_row is not None:
        assert_org_subtree_access(db, current_user, cohort_row.org_node_id)
    db.flush()
    affected_tasks = (
        db.query(TeachingTask)
        .filter(TeachingTask.semester_id == payload.semester_id, TeachingTask.is_locked.is_(False))
        .all()
    )
    refit_count = 0
    for t in affected_tasks:
        cids = list(t.cohort_ids or [])
        if payload.cohort_id in cids:
            bmask = get_cohort_blocked_mask(db, payload.semester_id, cids)
            new_mask, _, _ = fit_week_mask_to_hours(
                t.start_week, t.end_week, t.week_type, bmask, t.total_hours, t.weekly_sessions
            )
            t.week_mask = new_mask
            refit_count += 1
    db.commit()
    return {"status": "ok", "cohort_id": payload.cohort_id, "weeks": f"{payload.start_week}-{payload.end_week}", "mode": payload.week_mode}


@router.get("/effective-mask")
def compute_effective_mask_api(
    semester_id: int = Query(1),
    cohort_ids: str = Query(""),
    start_week: int = Query(1),
    end_week: int = Query(18),
    week_type: int = Query(0),
    db: Session = Depends(get_db),
):
    cids = [int(x) for x in cohort_ids.split(",") if x.strip().isdigit()]
    raw_mask = build_week_mask(start_week, end_week, week_type)
    blocked_mask = get_cohort_blocked_mask(db, semester_id, cids)
    eff_mask = subtract_blocked_weeks(raw_mask, blocked_mask)
    return {
        "raw_mask": raw_mask,
        "blocked_mask": blocked_mask,
        "effective_mask": eff_mask,
        "effective_label": mask_to_label(eff_mask),
    }
