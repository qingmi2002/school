"""从 PostgreSQL 16 张核心表加载 SolverInput，并将求解结果落库为新版本方案。"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.org_presets import resolve_campus_boundary_id
from app.models import (
    Classroom,
    OrgNode,
    OrgResourceGrant,
    PublicCourseLock,
    RoomCourseRule,
    ScheduleDetail,
    SchedulePlan,
    TeacherUnavailable,
    TeachingTask,
    Timeslot,
)
from app.solver.schemas import (
    SolverInput,
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

    # 1. 时间片加载（优先读取节点级覆写时间片，否则回退全校默认 org_node_id IS NULL）
    ts_rows = []
    if org_node_id is not None:
        ts_rows = db.query(Timeslot).filter(Timeslot.org_node_id == org_node_id).all()
    if not ts_rows:
        ts_rows = db.query(Timeslot).filter(Timeslot.org_node_id.is_(None)).all()

    # 2. 教室池加载（支持本节点专属 + 横向授权借用 + PUBLIC_POOL）
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

    # 3. 教学任务加载
    task_q = db.query(TeachingTask).filter(
        TeachingTask.semester_id == semester_id, TeachingTask.is_locked.is_(False)
    )
    if run_mode == "SINGLE_DEPT" and org_node_id is not None:
        task_q = task_q.filter(TeachingTask.org_node_id == org_node_id)
    task_rows = task_q.all()

    # 4. 分级基线锁定、教师禁排与机房黑白名单
    lock_rows = db.query(PublicCourseLock).filter(PublicCourseLock.semester_id == semester_id).all()
    unavail_rows = db.query(TeacherUnavailable).filter(TeacherUnavailable.semester_id == semester_id).all()
    room_ids = {r.id for r in room_rows}
    rule_rows = (
        db.query(RoomCourseRule).filter(RoomCourseRule.classroom_id.in_(room_ids)).all()
        if room_ids
        else []
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
                env_tags=list(r.env_tags or []),
            )
            for r in room_rows
        ],
        tasks=[
            SolverTask(
                id=t.id,
                org_node_id=t.org_node_id,
                course_code=t.course_code,
                course_name=t.course_name,
                course_category=t.course_category,
                teacher_id=t.teacher_id,
                cohort_ids=list(t.cohort_ids or []),
                weekly_sessions=t.weekly_sessions,
                week_type=t.week_type,
                total_students=t.total_students,
                required_env_tags=list(t.required_env_tags or []),
            )
            for t in task_rows
        ],
        public_locks=[
            SolverPublicLock(
                timeslot_id=l.timeslot_id,
                week_type=l.week_type,
                cohort_id=l.cohort_id,
                classroom_id=l.classroom_id,
                teacher_id=l.teacher_id,
                course_name=l.course_name,
            )
            for l in lock_rows
        ],
        teacher_unavailable=[
            SolverTeacherUnavailable(
                teacher_id=u.teacher_id,
                timeslot_id=u.timeslot_id,
                constraint_level=u.constraint_level,
                reason=u.reason,
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

    for item in result.assignments:
        db.add(
            ScheduleDetail(
                plan_id=plan.id,
                task_id=item.task_id,
                timeslot_id=item.timeslot_id,
                classroom_id=item.classroom_id,
                week_type=item.week_type,
                is_manual_adjusted=False,
            )
        )
    db.commit()
    db.refresh(plan)
    return plan
