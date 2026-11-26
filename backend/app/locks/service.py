"""
T2.2 分级基线锁定与自由下发核心服务
- 支持校级 / 学院 / 系部任意层级下发公共课只读锁定基线
- 沿 org_node.tree_path 自动向下继承生效，兄弟院系锁定互不误伤
- 单院系独立模式支持零校级锁跳过或自建系级锁定
- 严禁下级节点越权删除上级下发的只读锁定
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import OrgNode, PublicCourseLock, ScheduleDetail, SchedulePlan, TeachingTask
from app.locks.schemas import (
    BaselineLockBatchCreate,
    EffectiveBaselineLocksOut,
    EffectiveLockOut,
)


def upsert_baseline_locks(db: Session, payload: BaselineLockBatchCreate) -> List[PublicCourseLock]:
    scope_node = db.query(OrgNode).filter(OrgNode.id == payload.lock_scope_org_id).first()
    if scope_node is None:
        raise ValueError(f"锁定作用域组织节点 id={payload.lock_scope_org_id} 不存在")

    if payload.replace_existing:
        db.query(PublicCourseLock).filter(
            PublicCourseLock.semester_id == payload.semester_id,
            PublicCourseLock.lock_scope_org_id == payload.lock_scope_org_id,
        ).delete()

    created: List[PublicCourseLock] = []
    for item in payload.items:
        lock = PublicCourseLock(
            semester_id=payload.semester_id,
            lock_scope_org_id=payload.lock_scope_org_id,
            timeslot_id=item.timeslot_id,
            week_type=item.week_type,
            cohort_id=item.cohort_id,
            classroom_id=item.classroom_id,
            teacher_id=item.teacher_id,
            course_name=item.course_name,
            is_readonly=item.is_readonly,
        )
        db.add(lock)
        created.append(lock)

    db.commit()
    for row in created:
        db.refresh(row)
    return created


def publish_plan_as_baseline(
    db: Session,
    plan_id: int,
    lock_scope_org_id: Optional[int] = None,
    replace_existing: bool = True,
) -> List[PublicCourseLock]:
    """将已排定的公共课/院级课方案一键转化为只读基线锁定并下发给下级节点。"""
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if plan is None:
        raise ValueError(f"排课方案 id={plan_id} 不存在")

    scope_id = lock_scope_org_id if lock_scope_org_id is not None else plan.org_node_id
    details = db.query(ScheduleDetail).filter(ScheduleDetail.plan_id == plan_id).all()
    task_ids = {d.task_id for d in details}
    tasks_by_id = (
        {t.id: t for t in db.query(TeachingTask).filter(TeachingTask.id.in_(task_ids)).all()}
        if task_ids
        else {}
    )

    if replace_existing:
        db.query(PublicCourseLock).filter(
            PublicCourseLock.semester_id == plan.semester_id,
            PublicCourseLock.lock_scope_org_id == scope_id,
        ).delete()

    created: List[PublicCourseLock] = []
    for d in details:
        task = tasks_by_id.get(d.task_id)
        if task is None:
            continue
        cohorts = list(task.cohort_ids or [])
        if cohorts:
            for cid in cohorts:
                lock = PublicCourseLock(
                    semester_id=plan.semester_id,
                    lock_scope_org_id=scope_id,
                    timeslot_id=d.timeslot_id,
                    week_type=d.week_type,
                    cohort_id=cid,
                    classroom_id=d.classroom_id,
                    teacher_id=task.teacher_id,
                    course_name=task.course_name,
                    is_readonly=True,
                )
                db.add(lock)
                created.append(lock)
        else:
            lock = PublicCourseLock(
                semester_id=plan.semester_id,
                lock_scope_org_id=scope_id,
                timeslot_id=d.timeslot_id,
                week_type=d.week_type,
                cohort_id=None,
                classroom_id=d.classroom_id,
                teacher_id=task.teacher_id,
                course_name=task.course_name,
                is_readonly=True,
            )
            db.add(lock)
            created.append(lock)

    plan.is_published = True
    db.commit()
    return created


def get_effective_locks_for_node(
    db: Session,
    semester_id: int,
    target_org_node_id: Optional[int],
) -> EffectiveBaselineLocksOut:
    """
    查询对 target_org_node_id 生效的全部基线锁定：
    - 若 target_org_node_id 为 None（全校统筹模式）：返回全校该学期全部锁定。
    - 若指定了具体排课节点：沿 tree_path 向上溯源，自动继承所有祖先节点（校->校区->学院）以及本节点自身锁定；
      兄弟院系的系级局部锁定不会越界干扰。
    """
    nodes = db.query(OrgNode).all()
    node_map = {n.id: n for n in nodes}

    if target_org_node_id is None:
        rows = db.query(PublicCourseLock).filter(PublicCourseLock.semester_id == semester_id).all()
        return EffectiveBaselineLocksOut(
            semester_id=semester_id,
            target_org_node_id=0,
            total_locks=len(rows),
            locks=[
                EffectiveLockOut(
                    id=r.id,
                    semester_id=r.semester_id,
                    lock_scope_org_id=r.lock_scope_org_id,
                    lock_scope_org_name=node_map[r.lock_scope_org_id].node_name
                    if r.lock_scope_org_id in node_map
                    else str(r.lock_scope_org_id),
                    timeslot_id=r.timeslot_id,
                    week_type=r.week_type,
                    cohort_id=r.cohort_id,
                    classroom_id=r.classroom_id,
                    teacher_id=r.teacher_id,
                    course_name=r.course_name,
                    is_readonly=r.is_readonly,
                    inherited_from_ancestor=False,
                )
                for r in rows
            ],
        )

    target_node = node_map.get(target_org_node_id)
    if target_node is None:
        raise ValueError(f"目标组织节点 id={target_org_node_id} 不存在")

    ancestor_and_self_ids = {int(x) for x in target_node.tree_path.strip("/").split("/") if x}
    rows = (
        db.query(PublicCourseLock)
        .filter(
            PublicCourseLock.semester_id == semester_id,
            PublicCourseLock.lock_scope_org_id.in_(ancestor_and_self_ids),
        )
        .all()
    )

    return EffectiveBaselineLocksOut(
        semester_id=semester_id,
        target_org_node_id=target_org_node_id,
        total_locks=len(rows),
        locks=[
            EffectiveLockOut(
                id=r.id,
                semester_id=r.semester_id,
                lock_scope_org_id=r.lock_scope_org_id,
                lock_scope_org_name=node_map[r.lock_scope_org_id].node_name
                if r.lock_scope_org_id in node_map
                else str(r.lock_scope_org_id),
                timeslot_id=r.timeslot_id,
                week_type=r.week_type,
                cohort_id=r.cohort_id,
                classroom_id=r.classroom_id,
                teacher_id=r.teacher_id,
                course_name=r.course_name,
                is_readonly=r.is_readonly,
                inherited_from_ancestor=(r.lock_scope_org_id != target_org_node_id),
            )
            for r in rows
        ],
    )


def delete_baseline_lock(db: Session, lock_id: int, operator_org_node_id: int) -> None:
    """仅允许锁定所属层级或其上级节点管理员删除只读基线锁定，防止下级系部越权解锁。"""
    lock = db.query(PublicCourseLock).filter(PublicCourseLock.id == lock_id).first()
    if lock is None:
        raise ValueError(f"基线锁定记录 id={lock_id} 不存在")

    scope_node = db.query(OrgNode).filter(OrgNode.id == lock.lock_scope_org_id).first()
    op_node = db.query(OrgNode).filter(OrgNode.id == operator_org_node_id).first()
    if scope_node is None or op_node is None:
        raise PermissionError("无法校验操作者组织权限")

    # 只有当 lock 所在节点位于操作者节点或其子树下（即操作者同级或更高级），才允许解锁
    if not scope_node.tree_path.startswith(op_node.tree_path):
        raise PermissionError(
            f"无权解除上级节点【{scope_node.node_name}】下发的只读公共课锁定"
        )

    db.delete(lock)
    db.commit()
