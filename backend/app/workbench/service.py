"""T3.2 + T3.3 课表矩阵聚合视图与开课后调停课/代课审批流服务。"""
from collections import defaultdict
from typing import List

from sqlalchemy.orm import Session

from app.locks.service import get_effective_locks_for_node
from app.models import (
    Classroom,
    ScheduleChangeAudit,
    ScheduleDetail,
    SchedulePlan,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.workbench.schemas import (
    ChangeRequestCreate,
    ChangeRequestOut,
    ChangeRequestReview,
    MatrixCardOut,
    MatrixEntityOption,
    UnscheduledItemOut,
    WorkbenchViewOut,
)


def get_workbench_view(db: Session, plan_id: int) -> WorkbenchViewOut:
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if plan is None:
        raise ValueError(f"排课方案 id={plan_id} 不存在")

    ts_map = {t.id: t for t in db.query(Timeslot).all()}
    rooms = db.query(Classroom).filter(Classroom.is_active.is_(True)).all()
    room_map = {r.id: r for r in rooms}
    users = db.query(SysUser).all()
    user_map = {u.id: u for u in users}
    cohorts = db.query(StudentCohort).all()
    cohort_map = {c.id: c for c in cohorts}

    details = db.query(ScheduleDetail).filter(ScheduleDetail.plan_id == plan_id).all()
    tasks = db.query(TeachingTask).filter(
        TeachingTask.semester_id == plan.semester_id,
        TeachingTask.org_node_id == plan.org_node_id,
    ).all()
    task_map = {t.id: t for t in tasks}

    scheduled_count = defaultdict(int)
    cards: List[MatrixCardOut] = []

    for d in details:
        t = task_map.get(d.task_id) or db.query(TeachingTask).filter(TeachingTask.id == d.task_id).first()
        ts = ts_map.get(d.timeslot_id)
        rm = room_map.get(d.classroom_id)
        if not t or not ts or not rm:
            continue
        scheduled_count[t.id] += 1
        c_ids = list(t.cohort_ids or [])
        cards.append(
            MatrixCardOut(
                detail_id=d.id,
                task_id=t.id,
                timeslot_id=ts.id,
                day_of_week=ts.day_of_week,
                period_index=ts.period_index,
                classroom_id=rm.id,
                room_code=rm.room_code,
                course_code=t.course_code,
                course_name=t.course_name,
                course_category=t.course_category,
                teacher_id=t.teacher_id,
                teacher_name=user_map[t.teacher_id].real_name if t.teacher_id in user_map else f"教师#{t.teacher_id}",
                cohort_ids=c_ids,
                cohort_names=[cohort_map[cid].cohort_name if cid in cohort_map else f"班#{cid}" for cid in c_ids],
                week_type=d.week_type,
                is_locked=t.is_locked,
                is_manual_adjusted=d.is_manual_adjusted,
            )
        )

    # 叠加分级只读公共课锁定块（灰色不可拖拽）
    eff_locks = get_effective_locks_for_node(
        db,
        semester_id=plan.semester_id,
        target_org_node_id=plan.org_node_id if plan.run_mode == "SINGLE_DEPT" else None,
    )
    for lk in eff_locks.locks:
        ts = ts_map.get(lk.timeslot_id)
        if not ts:
            continue
        rm = room_map.get(lk.classroom_id) if lk.classroom_id else None
        cards.append(
            MatrixCardOut(
                detail_id=-lk.id,
                task_id=0,
                timeslot_id=ts.id,
                day_of_week=ts.day_of_week,
                period_index=ts.period_index,
                classroom_id=lk.classroom_id or 0,
                room_code=rm.room_code if rm else "公共教室",
                course_code="PUBLIC",
                course_name=lk.course_name,
                course_category="THEORY",
                teacher_id=lk.teacher_id or 0,
                teacher_name=user_map[lk.teacher_id].real_name if lk.teacher_id in user_map else "校级统筹",
                cohort_ids=[lk.cohort_id] if lk.cohort_id else [],
                cohort_names=[cohort_map[lk.cohort_id].cohort_name] if lk.cohort_id in cohort_map else [],
                week_type=lk.week_type,
                is_locked=True,
                is_manual_adjusted=False,
                lock_source=lk.lock_scope_org_name,
            )
        )

    unscheduled: List[UnscheduledItemOut] = []
    for t in tasks:
        if t.is_locked:
            continue
        got = scheduled_count.get(t.id, 0)
        if got < t.weekly_sessions:
            unscheduled.append(
                UnscheduledItemOut(
                    task_id=t.id,
                    course_code=t.course_code,
                    course_name=t.course_name,
                    teacher_name=user_map[t.teacher_id].real_name if t.teacher_id in user_map else f"教师#{t.teacher_id}",
                    weekly_sessions=t.weekly_sessions,
                    scheduled_sessions=got,
                    reason="存在硬约束冲突或机房容量不足，待人工微调释放槽位",
                )
            )

    return WorkbenchViewOut(
        plan_id=plan.id,
        plan_name=plan.plan_name,
        semester_id=plan.semester_id,
        org_node_id=plan.org_node_id,
        run_mode=plan.run_mode,
        cohorts=[MatrixEntityOption(id=c.id, label=c.cohort_name, sub_label=f"{c.student_count}人") for c in cohorts],
        teachers=[
            MatrixEntityOption(id=u.id, label=u.real_name, sub_label=u.username)
            for u in users
            if u.role_code == "TEACHER"
        ],
        rooms=[MatrixEntityOption(id=r.id, label=r.room_code, sub_label=f"{r.capacity}座") for r in rooms],
        cards=cards,
        unscheduled=unscheduled,
    )


def create_change_request(db: Session, payload: ChangeRequestCreate) -> ChangeRequestOut:
    audit = ScheduleChangeAudit(
        plan_id=payload.plan_id,
        operator_id=payload.operator_id,
        audit_type="CHANGE_REQUEST",
        status="PENDING",
        payload={
            "change_type": payload.change_type,
            "detail_id": payload.detail_id,
            "target_timeslot_id": payload.target_timeslot_id,
            "target_classroom_id": payload.target_classroom_id,
            "substitute_teacher_id": payload.substitute_teacher_id,
            "reason": payload.reason,
        },
        remark=payload.reason,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return ChangeRequestOut(
        id=audit.id,
        plan_id=audit.plan_id,
        operator_id=audit.operator_id,
        status=audit.status,
        change_type=payload.change_type,
        detail_id=payload.detail_id,
        reason=payload.reason,
    )


def review_change_request(
    db: Session, audit_id: int, review: ChangeRequestReview
) -> ChangeRequestOut:
    audit = (
        db.query(ScheduleChangeAudit)
        .filter(ScheduleChangeAudit.id == audit_id, ScheduleChangeAudit.audit_type == "CHANGE_REQUEST")
        .first()
    )
    if audit is None:
        raise ValueError(f"调停课审批单 id={audit_id} 不存在")
    if audit.status != "PENDING":
        raise ValueError(f"审批单当前状态为 {audit.status}，不可重复审批")

    audit.status = review.decision
    if review.review_note:
        audit.remark = review.review_note

    p = audit.payload or {}
    if review.decision == "APPROVED" and p.get("change_type") == "RESCHEDULE":
        det = db.query(ScheduleDetail).filter(ScheduleDetail.id == p.get("detail_id")).first()
        if det and p.get("target_timeslot_id") and p.get("target_classroom_id"):
            det.timeslot_id = p["target_timeslot_id"]
            det.classroom_id = p["target_classroom_id"]
            det.is_manual_adjusted = True

    db.commit()
    db.refresh(audit)
    return ChangeRequestOut(
        id=audit.id,
        plan_id=audit.plan_id,
        operator_id=audit.operator_id,
        status=audit.status,
        change_type=p.get("change_type", "RESCHEDULE"),
        detail_id=p.get("detail_id", 0),
        reason=p.get("reason", ""),
        review_note=audit.remark,
    )


def list_change_requests(db: Session, plan_id: int) -> List[ChangeRequestOut]:
    rows = (
        db.query(ScheduleChangeAudit)
        .filter(ScheduleChangeAudit.plan_id == plan_id, ScheduleChangeAudit.audit_type == "CHANGE_REQUEST")
        .order_by(ScheduleChangeAudit.id.desc())
        .all()
    )
    out: List[ChangeRequestOut] = []
    for r in rows:
        p = r.payload or {}
        out.append(
            ChangeRequestOut(
                id=r.id,
                plan_id=r.plan_id,
                operator_id=r.operator_id,
                status=r.status,
                change_type=p.get("change_type", "RESCHEDULE"),
                detail_id=p.get("detail_id", 0),
                reason=p.get("reason", ""),
                review_note=r.remark,
            )
        )
    return out
