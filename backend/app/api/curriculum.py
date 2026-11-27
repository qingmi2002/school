"""V1.5 + V1.6 课程库、学期总课时耦合、本学期班级选课、多班指定合班与教师负荷统计 API。"""
from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.week_mask import build_week_mask, fit_week_mask_to_hours, mask_to_label, mask_to_weeks, weeks_to_mask
from app.db.session import get_db
from app.models import CohortWeekPlan, Course, OrgNode, Semester, StudentCohort, SysUser, TeachingTask

router = APIRouter(prefix="/curriculum", tags=["curriculum-and-tasks"])


class CourseCreateIn(BaseModel):
    owner_org_id: Optional[int] = None
    course_code: str
    course_name: str
    course_category: str = "THEORY"
    required_room_type: str = "NORMAL"
    default_weekly_sessions: int = 2
    default_total_hours: int = 32  # V1.6 默认学期总学时
    allow_combined: bool = True


class TeachingTaskCreateIn(BaseModel):
    semester_id: Optional[int] = None
    org_node_id: Optional[int] = None
    course_id: Optional[int] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    course_category: Optional[str] = None
    required_room_type: Optional[str] = None
    teacher_id: int
    cohort_ids: List[int] = Field(min_length=1)
    weekly_sessions: Optional[int] = None
    total_hours: Optional[int] = None  # V1.6 学期总学时（自动结合周历推算精确周次）
    prefer_consecutive: bool = False  # V1.6 实验/上机连堂偏好
    week_type: int = 0
    start_week: int = 1
    end_week: int = 18
    total_students: Optional[int] = None
    required_env_tags: List[str] = Field(default_factory=list)


class MergeTasksIn(BaseModel):
    task_ids: List[int] = Field(min_length=2)
    teacher_id: Optional[int] = None
    required_room_type: Optional[str] = None


def _get_union_blocked_mask(db: Session, semester_id: int, cohort_ids: List[int]) -> int:
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
    return weeks_to_mask([r.week_no for r in rows])


@router.get("/courses")
def list_courses(owner_org_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(Course).filter(Course.is_active.is_(True))
    if owner_org_id is not None:
        q = q.filter(Course.owner_org_id == owner_org_id)
    rows = q.order_by(Course.course_code).all()
    return [
        {
            "id": c.id,
            "owner_org_id": c.owner_org_id,
            "course_code": c.course_code,
            "course_name": c.course_name,
            "course_category": c.course_category,
            "required_room_type": c.required_room_type,
            "default_weekly_sessions": c.default_weekly_sessions,
            "default_total_hours": int(getattr(c, "default_total_hours", 32) or 32),
            "allow_combined": c.allow_combined,
        }
        for c in rows
    ]


@router.post("/courses")
def create_course(payload: CourseCreateIn, db: Session = Depends(get_db)):
    exists = db.query(Course).filter(Course.course_code == payload.course_code.strip()).first()
    if exists:
        raise HTTPException(status_code=400, detail=f"课程代码 {payload.course_code} 已存在")
    org_id = payload.owner_org_id
    if org_id is None:
        first_org = db.query(OrgNode).filter(OrgNode.is_active.is_(True)).order_by(OrgNode.id).first()
        if first_org is None:
            raise HTTPException(status_code=400, detail="请先创建组织节点")
        org_id = first_org.id
    row = Course(
        owner_org_id=org_id,
        course_code=payload.course_code.strip(),
        course_name=payload.course_name.strip(),
        course_category=payload.course_category,
        required_room_type=payload.required_room_type,
        default_weekly_sessions=payload.default_weekly_sessions,
        default_total_hours=payload.default_total_hours,
        allow_combined=payload.allow_combined,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "owner_org_id": row.owner_org_id,
        "course_code": row.course_code,
        "course_name": row.course_name,
        "course_category": row.course_category,
        "required_room_type": row.required_room_type,
        "default_weekly_sessions": row.default_weekly_sessions,
        "default_total_hours": row.default_total_hours,
        "allow_combined": row.allow_combined,
    }


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db)):
    row = db.query(Course).filter(Course.id == course_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    row.is_active = False
    db.commit()
    return {"deleted": True, "id": course_id}


def _serialize_task(t: TeachingTask, teacher_map: dict, cohort_map: dict) -> dict:
    cids = list(t.cohort_ids or [])
    c_names = [cohort_map[cid].cohort_name for cid in cids if cid in cohort_map]
    teacher = teacher_map.get(t.teacher_id)
    eff_mask = t.week_mask if t.week_mask is not None else build_week_mask(t.start_week, t.end_week, t.week_type)
    eff_weeks = len(mask_to_weeks(eff_mask))
    planned_actual_hours = eff_weeks * int(t.weekly_sessions or 1) * 2
    target_hours = getattr(t, "total_hours", None)
    return {
        "id": t.id,
        "semester_id": t.semester_id,
        "org_node_id": t.org_node_id,
        "course_id": t.course_id,
        "course_code": t.course_code,
        "course_name": t.course_name,
        "course_category": t.course_category,
        "required_room_type": t.required_room_type,
        "teacher_id": t.teacher_id,
        "teacher_name": teacher.real_name if teacher else f"教师#{t.teacher_id}",
        "cohort_ids": cids,
        "cohort_names": c_names,
        "is_combined": len(cids) >= 2,
        "weekly_sessions": t.weekly_sessions,
        "total_hours": target_hours,
        "planned_actual_hours": planned_actual_hours,
        "hours_sufficient": (target_hours is None) or (planned_actual_hours >= target_hours),
        "effective_weeks_label": mask_to_label(eff_mask),
        "prefer_consecutive": bool(getattr(t, "prefer_consecutive", False)),
        "week_type": t.week_type,
        "start_week": t.start_week,
        "end_week": t.end_week,
        "total_students": t.total_students,
        "is_locked": t.is_locked,
    }


@router.get("/tasks")
def list_teaching_tasks(
    semester_id: Optional[int] = Query(None),
    cohort_id: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(TeachingTask)
    if semester_id is not None:
        q = q.filter(TeachingTask.semester_id == semester_id)
    if teacher_id is not None:
        q = q.filter(TeachingTask.teacher_id == teacher_id)
    rows = q.order_by(TeachingTask.id.desc()).all()
    if cohort_id is not None:
        rows = [r for r in rows if cohort_id in (r.cohort_ids or [])]

    teacher_map = {u.id: u for u in db.query(SysUser).all()}
    cohort_map = {c.id: c for c in db.query(StudentCohort).all()}
    return [_serialize_task(r, teacher_map, cohort_map) for r in rows]


@router.post("/tasks")
def create_teaching_task(payload: TeachingTaskCreateIn, db: Session = Depends(get_db)):
    sem = (
        db.query(Semester).filter(Semester.id == payload.semester_id).first()
        if payload.semester_id
        else db.query(Semester).filter(Semester.is_current.is_(True)).first() or db.query(Semester).first()
    )
    if sem is None:
        raise HTTPException(status_code=400, detail="请先创建学期")

    teacher = db.query(SysUser).filter(SysUser.id == payload.teacher_id).first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="任课教师不存在")

    cohorts = db.query(StudentCohort).filter(StudentCohort.id.in_(payload.cohort_ids)).all()
    if len(cohorts) != len(set(payload.cohort_ids)):
        raise HTTPException(status_code=400, detail="包含无效的班级 ID")

    course = db.query(Course).filter(Course.id == payload.course_id).first() if payload.course_id else None
    if course and len(set(payload.cohort_ids)) >= 2 and not course.allow_combined:
        raise HTTPException(status_code=400, detail=f"课程《{course.course_name}》设置为不允许合班上课")

    course_code = payload.course_code or (course.course_code if course else None)
    course_name = payload.course_name or (course.course_name if course else None)
    if not course_code or not course_name:
        raise HTTPException(status_code=400, detail="请先选择课程或填写课程代码与名称")

    course_category = payload.course_category or (course.course_category if course else "THEORY")
    required_room_type = payload.required_room_type or (course.required_room_type if course else None)
    weekly_sessions = payload.weekly_sessions or (course.default_weekly_sessions if course else 2)
    target_hours = payload.total_hours if payload.total_hours is not None else (
        int(getattr(course, "default_total_hours", 32) or 32) if course else None
    )
    auto_students = sum(int(c.student_count or 40) for c in cohorts)
    total_students = payload.total_students if payload.total_students is not None else auto_students
    org_node_id = payload.org_node_id or cohorts[0].org_node_id
    sorted_cids = sorted(set(payload.cohort_ids))

    blocked_mask = _get_union_blocked_mask(db, sem.id, sorted_cids)
    eff_mask, _, _ = fit_week_mask_to_hours(
        payload.start_week, payload.end_week, payload.week_type, blocked_mask, target_hours, weekly_sessions
    )

    task = TeachingTask(
        semester_id=sem.id,
        org_node_id=org_node_id,
        course_id=course.id if course else None,
        course_code=course_code,
        course_name=course_name,
        course_category=course_category,
        required_room_type=required_room_type,
        teacher_id=teacher.id,
        cohort_ids=sorted_cids,
        weekly_sessions=weekly_sessions,
        total_hours=target_hours,
        prefer_consecutive=payload.prefer_consecutive,
        week_type=payload.week_type,
        start_week=payload.start_week,
        end_week=payload.end_week,
        week_mask=eff_mask,
        total_students=total_students,
        required_env_tags=payload.required_env_tags,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _serialize_task(task, {teacher.id: teacher}, {c.id: c for c in cohorts})


@router.post("/tasks/merge")
def merge_tasks_into_combined(payload: MergeTasksIn, db: Session = Depends(get_db)):
    tasks = db.query(TeachingTask).filter(TeachingTask.id.in_(payload.task_ids)).all()
    if len(tasks) < 2:
        raise HTTPException(status_code=400, detail="请至少选择 2 条教学任务进行合班")

    course_codes = {t.course_code for t in tasks}
    if len(course_codes) > 1:
        raise HTTPException(status_code=400, detail="只能对同一门课程的任务执行合班合并")

    base = tasks[0]
    merged_cohorts = sorted({cid for t in tasks for cid in (t.cohort_ids or [])})
    cohort_rows = db.query(StudentCohort).filter(StudentCohort.id.in_(merged_cohorts)).all()
    total_students = sum(int(c.student_count or 40) for c in cohort_rows)

    base.cohort_ids = merged_cohorts
    base.total_students = total_students
    if payload.teacher_id is not None:
        base.teacher_id = payload.teacher_id
    if payload.required_room_type is not None:
        base.required_room_type = payload.required_room_type

    blocked_mask = _get_union_blocked_mask(db, base.semester_id, merged_cohorts)
    eff_mask, _, _ = fit_week_mask_to_hours(
        base.start_week, base.end_week, base.week_type, blocked_mask, base.total_hours, base.weekly_sessions
    )
    base.week_mask = eff_mask

    for extra in tasks[1:]:
        db.delete(extra)

    db.commit()
    db.refresh(base)
    teacher_map = {u.id: u for u in db.query(SysUser).filter(SysUser.id == base.teacher_id).all()}
    cohort_map = {c.id: c for c in cohort_rows}
    return _serialize_task(base, teacher_map, cohort_map)


@router.delete("/tasks/{task_id}")
def delete_teaching_task(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TeachingTask).filter(TeachingTask.id == task_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="教学任务不存在")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": task_id}


@router.get("/teacher-workload")
def get_teacher_workload(semester_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(TeachingTask)
    if semester_id is not None:
        q = q.filter(TeachingTask.semester_id == semester_id)
    tasks = q.all()
    teacher_map = {u.id: u for u in db.query(SysUser).all()}
    cohort_map = {c.id: c for c in db.query(StudentCohort).all()}

    grouped = defaultdict(list)
    for t in tasks:
        grouped[t.teacher_id].append(t)

    result = []
    for tid, t_list in grouped.items():
        u = teacher_map.get(tid)
        courses = sorted({f"{t.course_name}({t.course_code})" for t in t_list})
        cohorts = sorted({cohort_map[cid].cohort_name for t in t_list for cid in (t.cohort_ids or []) if cid in cohort_map})
        total_sem_hours = 0
        for t in t_list:
            eff_mask = t.week_mask if t.week_mask is not None else build_week_mask(t.start_week, t.end_week, t.week_type)
            total_sem_hours += len(mask_to_weeks(eff_mask)) * int(t.weekly_sessions or 1) * 2
        result.append(
            {
                "teacher_id": tid,
                "teacher_name": u.real_name if u else f"教师#{tid}",
                "role_code": u.role_code if u else "TEACHER",
                "teacher_priority": int(getattr(u, "teacher_priority", 1) or 1) if u else 1,
                "task_count": len(t_list),
                "combined_task_count": sum(1 for t in t_list if len(t.cohort_ids or []) >= 2),
                "total_weekly_sessions": sum(int(t.weekly_sessions or 0) for t in t_list),
                "total_semester_hours": total_sem_hours,
                "courses": courses,
                "cohorts": cohorts,
            }
        )
    result.sort(key=lambda x: (-x["total_semester_hours"], -x["total_weekly_sessions"], x["teacher_id"]))
    return result
