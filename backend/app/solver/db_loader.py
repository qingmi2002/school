"""从 PostgreSQL 核心表加载 SolverInput（已集成 V1.6 全套 6 项优化：周期规则、精确周次掩码、已锁课避让、自有教室优先），并将求解结果落库。"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.week_mask import build_week_mask, fit_week_mask_to_hours, subtract_blocked_weeks, weeks_to_mask
from app.db.org_presets import resolve_campus_boundary_id
from app.locks.service import get_effective_locks_for_node
from app.models import (
    Classroom,
    CohortWeekPlan,
    OrgNode,
    OrgResourceGrant,
    RoomCourseRule,
    ScheduleDetail,
    SchedulePlan,
    SchedulePolicyRule,
    SysUser,
    TeacherUnavailable,
    TeachingTask,
    Timeslot,
)
from app.solver.schemas import (
    SolverInput,
    SolverPolicyRule,
    SolverPublicLock,
    SolverResult,
    SolverRoom,
    SolverRoomRule,
    SolverTask,
    SolverTeacherUnavailable,
    SolverTimeslot,
)


def load_solver_input_from_db(
    db: Session,
    semester_id: int,
    org_node_id: Optional[int] = None,
    run_mode: str = "SINGLE_DEPT",
    time_limit_seconds: float = 10.0,
) -> SolverInput:
    all_nodes = db.query(OrgNode).filter(OrgNode.is_active.is_(True)).all()
    node_map = {n.id: n for n in all_nodes}

    # 1. 时间片加载
    ts_rows = []
    if org_node_id is not None:
        ts_rows = db.query(Timeslot).filter(Timeslot.org_node_id == org_node_id).all()
    if not ts_rows:
        ts_rows = db.query(Timeslot).filter(Timeslot.org_node_id.is_(None)).all()

    # 2. 教室池加载
    room_query = db.query(Classroom).filter(Classroom.is_active.is_(True))
    if run_mode == "SINGLE_DEPT" and org_node_id is not None:
        granted_org_ids = [
            g.granter_org_id
            for g in db.query(OrgResourceGrant)
            .filter(
                OrgResourceGrant.grantee_org_id == org_node_id,
                OrgResourceGrant.resource_type == "ROOM_POOL",
                OrgResourceGrant.is_active.is_(True),
            )
            .all()
        ]
        allowed_owner_ids = set(granted_org_ids) | {org_node_id}
        room_rows = [
            r
            for r in room_query.all()
            if r.owner_org_id in allowed_owner_ids or r.sharing_policy == "PUBLIC_POOL"
        ]
    else:
        room_rows = room_query.all()

    # 3. 教学任务加载（未锁定任务进入排课；已锁定任务的已有排课转为只读占坑避让）
    base_task_q = db.query(TeachingTask).filter(TeachingTask.semester_id == semester_id)
    if run_mode == "SINGLE_DEPT" and org_node_id is not None:
        base_task_q = base_task_q.filter(TeachingTask.org_node_id == org_node_id)
    all_scope_tasks = base_task_q.all()
    task_rows = [t for t in all_scope_tasks if not t.is_locked]
    locked_task_map = {t.id: t for t in all_scope_tasks if t.is_locked}

    # 4. V1.4/V1.6 班级整周实训/考试/假期阻塞掩码加载
    blocked_by_cohort: dict[int, int] = {}
    for wp in (
        db.query(CohortWeekPlan)
        .filter(CohortWeekPlan.semester_id == semester_id, CohortWeekPlan.week_mode != "REGULAR")
        .all()
    ):
        blocked_by_cohort[wp.cohort_id] = blocked_by_cohort.get(wp.cohort_id, 0) | weeks_to_mask([wp.week_no])

    # 5. 分级公共课锁定 + V1.6 优化3：已锁定课程的已有课表自动转只读占坑避让
    effective_locks = get_effective_locks_for_node(
        db=db,
        semester_id=semester_id,
        target_org_node_id=org_node_id if run_mode == "SINGLE_DEPT" else None,
    )
    public_locks = [
        SolverPublicLock(
            timeslot_id=l.timeslot_id,
            week_type=l.week_type,
            cohort_id=l.cohort_id,
            classroom_id=l.classroom_id,
            teacher_id=l.teacher_id,
            course_name=l.course_name,
        )
        for l in effective_locks.locks
    ]

    if locked_task_map:
        latest_plan_q = db.query(SchedulePlan).filter(SchedulePlan.semester_id == semester_id)
        if run_mode == "SINGLE_DEPT" and org_node_id is not None:
            latest_plan_q = latest_plan_q.filter(SchedulePlan.org_node_id == org_node_id)
        latest_plan = latest_plan_q.order_by(SchedulePlan.id.desc()).first()
        if latest_plan is not None:
            locked_details = (
                db.query(ScheduleDetail)
                .filter(
                    ScheduleDetail.plan_id == latest_plan.id,
                    ScheduleDetail.task_id.in_(list(locked_task_map.keys())),
                )
                .all()
            )
            for d in locked_details:
                lt = locked_task_map[d.task_id]
                cids = list(lt.cohort_ids or []) or [None]
                for cid in cids:
                    public_locks.append(
                        SolverPublicLock(
                            timeslot_id=d.timeslot_id,
                            week_type=d.week_type,
                            cohort_id=cid,
                            classroom_id=d.classroom_id,
                            teacher_id=lt.teacher_id,
                            course_name=f"[已锁定]{lt.course_name}",
                        )
                    )

    # 6. 教师禁排、优先级与机房黑白名单
    unavail_rows = db.query(TeacherUnavailable).filter(TeacherUnavailable.semester_id == semester_id).all()
    teacher_prio_map = {u.id: int(getattr(u, "teacher_priority", 1) or 1) for u in db.query(SysUser).all()}
    room_ids = {r.id for r in room_rows}
    rule_rows = (
        db.query(RoomCourseRule).filter(RoomCourseRule.classroom_id.in_(room_ids)).all()
        if room_ids
        else []
    )

    # 7. V1.6 优化1：加载周期必排/禁排/偏好策略规则
    policy_rows = (
        db.query(SchedulePolicyRule)
        .filter(
            SchedulePolicyRule.is_active.is_(True),
            (SchedulePolicyRule.semester_id == semester_id) | (SchedulePolicyRule.semester_id.is_(None)),
        )
        .all()
    )

    solver_tasks = []
    for t in task_rows:
        cids = list(t.cohort_ids or [])
        union_blocked = 0
        for cid in cids:
            union_blocked |= blocked_by_cohort.get(cid, 0)
        if t.week_mask is not None:
            eff_mask = subtract_blocked_weeks(t.week_mask, union_blocked)
        elif getattr(t, "total_hours", None):
            eff_mask, _, _ = fit_week_mask_to_hours(
                t.start_week, t.end_week, t.week_type, union_blocked, t.total_hours, t.weekly_sessions
            )
        else:
            eff_mask = subtract_blocked_weeks(build_week_mask(t.start_week, t.end_week, t.week_type), union_blocked)
        if eff_mask == 0:
            eff_mask = build_week_mask(t.start_week, t.end_week, t.week_type)

        solver_tasks.append(
            SolverTask(
                id=t.id,
                org_node_id=t.org_node_id,
                course_code=t.course_code,
                course_name=t.course_name,
                course_category=t.course_category,
                teacher_id=t.teacher_id,
                cohort_ids=cids,
                weekly_sessions=t.weekly_sessions,
                week_type=t.week_type,
                week_mask=eff_mask,
                total_students=t.total_students,
                required_room_type=getattr(t, "required_room_type", None),
                teacher_priority=teacher_prio_map.get(t.teacher_id, 1),
                prefer_consecutive=bool(getattr(t, "prefer_consecutive", False)),
                required_env_tags=list(t.required_env_tags or []),
            )
        )

    return SolverInput(
        run_mode=run_mode,
        time_limit_seconds=time_limit_seconds,
        timeslots=[
            SolverTimeslot(
                id=t.id,
                day_of_week=t.day_of_week,
                period_index=t.period_index,
                period_name=t.period_name,
                is_evening=t.is_evening,
            )
            for t in ts_rows
        ],
        rooms=[
            SolverRoom(
                id=r.id,
                room_code=r.room_code,
                owner_org_id=r.owner_org_id,
                campus_boundary_id=resolve_campus_boundary_id(node_map, r.owner_org_id),
                capacity=r.capacity,
                room_type=r.room_type,
                usage_mode=getattr(r, "usage_mode", "FLOATING") or "FLOATING",
                fixed_cohort_id=getattr(r, "fixed_cohort_id", None),
                sharing_policy=getattr(r, "sharing_policy", "IDLE_BORROW") or "IDLE_BORROW",
                env_tags=list(r.env_tags or []),
            )
            for r in room_rows
        ],
        tasks=solver_tasks,
        public_locks=public_locks,
        teacher_unavailable=[
            SolverTeacherUnavailable(
                teacher_id=u.teacher_id,
                timeslot_id=u.timeslot_id,
                constraint_level=u.constraint_level,
                reason=u.reason,
                week_mask=getattr(u, "week_mask", None),
            )
            for u in unavail_rows
        ],
        room_rules=[
            SolverRoomRule(
                classroom_id=r.classroom_id,
                course_code=r.course_code,
                course_category=r.course_category,
                rule_type=r.rule_type,
            )
            for r in rule_rows
        ],
        policy_rules=[
            SolverPolicyRule(
                target_type=pr.target_type,
                target_id=pr.target_id,
                rule_type=pr.rule_type,
                day_of_week=pr.day_of_week,
                period_index=pr.period_index,
                priority=int(getattr(pr, "priority", 10) or 10),
            )
            for pr in policy_rows
        ],
    )


def persist_solver_result(
    db: Session,
    semester_id: int,
    org_node_id: int,
    plan_name: str,
    run_mode: str,
    result: SolverResult,
) -> SchedulePlan:
    version_tag = f"V_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    plan = SchedulePlan(
        semester_id=semester_id,
        org_node_id=org_node_id,
        plan_name=plan_name,
        version_tag=version_tag,
        run_mode=run_mode,
        fitness_score=result.fitness_score,
        is_published=False,
    )
    db.add(plan)
    db.flush()

    task_masks = {
        t.id: t.week_mask
        for t in db.query(TeachingTask).filter(TeachingTask.semester_id == semester_id).all()
    }
    for item in result.assignments:
        db.add(
            ScheduleDetail(
                plan_id=plan.id,
                task_id=item.task_id,
                timeslot_id=item.timeslot_id,
                classroom_id=item.classroom_id,
                week_type=item.week_type,
                week_mask=task_masks.get(item.task_id),
                is_manual_adjusted=False,
            )
        )
    db.commit()
    db.refresh(plan)
    return plan
