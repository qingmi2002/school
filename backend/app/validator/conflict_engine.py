"""
T3.1 后端毫秒级（<50ms）红绿灯实时冲突校验器与全校/单院系一键体检引擎
7 重硬/软防线：
1. 教师硬/软禁排
2. 分级公共课只读锁定（沿 org_node.tree_path 继承）
3. 机房容量与软件环境标签匹配
4. 机房黑白名单规则
5. 横向资源借用授权（直属 / 祖先继承 / org_resource_grant / PUBLIC_POOL）
6. 时空唯一性与单双周复用（单周与双周互不冲突）
7. 跨校区相邻节次通勤熔断（基于 org_node.is_campus_boundary 溯源）
"""
from collections import defaultdict
import time
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.core.week_mask import build_week_mask, masks_overlap
from app.db.org_presets import resolve_campus_boundary_id
from app.locks.service import get_effective_locks_for_node
from app.models import (
    Classroom,
    OrgNode,
    RoomCourseRule,
    ScheduleDetail,
    SchedulePlan,
    SchedulePolicyRule,
    TeacherUnavailable,
    TeachingTask,
    Timeslot,
)
from app.org.service import authorize_resource_access
from app.validator.schemas import (
    DragCheckRequest,
    HealthCheckIssue,
    HealthCheckReport,
    MatrixLightsRequest,
    MatrixLightsResponse,
    SlotLightResult,
)


def _weeks_overlap(w1: int, w2: int) -> bool:
    return w1 == 0 or w2 == 0 or w1 == w2


class _PlanSnapshot:
    """单次校验构建的轻量内存哈希快照，确保多次槽位判定在 1~5ms 内完成。"""

    def __init__(self, db: Session, plan: SchedulePlan, scope: str):
        self.db = db
        self.plan = plan
        self.scope = scope

        nodes = db.query(OrgNode).all()
        self.node_map: Dict[int, OrgNode] = {n.id: n for n in nodes}

        ts_rows = db.query(Timeslot).all()
        self.ts_by_id: Dict[int, Timeslot] = {t.id: t for t in ts_rows}

        rooms = db.query(Classroom).all()
        self.room_by_id: Dict[int, Classroom] = {r.id: r for r in rooms}
        self.room_campus: Dict[int, Optional[int]] = {
            r.id: resolve_campus_boundary_id(self.node_map, r.owner_org_id) for r in rooms
        }

        # 机房黑白名单索引
        self.allow_rules: Dict[int, List[RoomCourseRule]] = defaultdict(list)
        self.deny_rules: Dict[int, List[RoomCourseRule]] = defaultdict(list)
        for rl in db.query(RoomCourseRule).all():
            if rl.rule_type == "ALLOW":
                self.allow_rules[rl.classroom_id].append(rl)
            else:
                self.deny_rules[rl.classroom_id].append(rl)

        # 教师禁排索引（V1.7 支持分周次 week_mask 精准校验）
        self.teacher_unavail: Dict[Tuple[int, int], List[Tuple[str, Optional[str], Optional[int]]]] = defaultdict(list)
        for u in db.query(TeacherUnavailable).filter(
            TeacherUnavailable.semester_id == plan.semester_id
        ).all():
            self.teacher_unavail[(u.teacher_id, u.timeslot_id)].append(
                (u.constraint_level, u.reason, getattr(u, 'week_mask', None))
            )

        # V1.7 周期策略规则索引
        self.policy_rules = (
            db.query(SchedulePolicyRule)
            .filter(
                SchedulePolicyRule.is_active.is_(True),
                (SchedulePolicyRule.semester_id == plan.semester_id) | (SchedulePolicyRule.semester_id.is_(None)),
            )
            .all()
        )

        # 分级公共课锁定索引
        effective_locks = get_effective_locks_for_node(
            db,
            semester_id=plan.semester_id,
            target_org_node_id=plan.org_node_id if scope == "SINGLE_DEPT" else None,
        )
        self.locks_by_ts: Dict[int, list] = defaultdict(list)
        for lk in effective_locks.locks:
            self.locks_by_ts[lk.timeslot_id].append(lk)

        # 课表明细与任务快照（SCHOOL_WIDE 纳入同校其他已发布方案，捕捉跨系兼课撞车）
        plan_ids = {plan.id}
        if scope == "SCHOOL_WIDE":
            other_plans = (
                db.query(SchedulePlan.id)
                .filter(
                    SchedulePlan.semester_id == plan.semester_id,
                    SchedulePlan.is_published.is_(True),
                )
                .all()
            )
            plan_ids.update(r[0] for r in other_plans)

        self.details: List[ScheduleDetail] = (
            db.query(ScheduleDetail).filter(ScheduleDetail.plan_id.in_(plan_ids)).all()
        )
        task_ids = {d.task_id for d in self.details}
        self.task_by_id: Dict[int, TeachingTask] = (
            {t.id: t for t in db.query(TeachingTask).filter(TeachingTask.id.in_(task_ids)).all()}
            if task_ids
            else {}
        )

        # 按 timeslot_id 建内存倒排索引
        self.details_by_ts: Dict[int, List[ScheduleDetail]] = defaultdict(list)
        self.teacher_day_period_campuses: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = defaultdict(list)
        for d in self.details:
            self.details_by_ts[d.timeslot_id].append(d)
            t = self.task_by_id.get(d.task_id)
            ts = self.ts_by_id.get(d.timeslot_id)
            c_id = self.room_campus.get(d.classroom_id)
            if t and ts and c_id is not None:
                self.teacher_day_period_campuses[(t.teacher_id, ts.day_of_week, ts.period_index)].append(
                    (d.id, d.week_type, c_id)
                )

    def evaluate_slot(
        self,
        detail: ScheduleDetail,
        task: TeachingTask,
        target_ts_id: int,
        target_room_id: int,
    ) -> Tuple[List[str], List[str]]:
        hard: List[str] = []
        soft: List[str] = []

        target_ts = self.ts_by_id.get(target_ts_id)
        target_room = self.room_by_id.get(target_room_id)
        if target_ts is None:
            return [f"目标时间片 id={target_ts_id} 不存在"], []
        if target_room is None:
            return [f"目标教室/机房 id={target_room_id} 不存在"], []

        # 1. 教师硬/软禁排（V1.7 精确 week_mask 对齐）
        full_m = build_week_mask(1, 30, 0)
        det_mask = getattr(detail, 'week_mask', None) or getattr(task, 'week_mask', None) or build_week_mask(task.start_week, task.end_week, detail.week_type)
        for level, reason, u_mask in self.teacher_unavail.get((task.teacher_id, target_ts_id), []):
            if masks_overlap(det_mask, u_mask if u_mask is not None else full_m):
                suffix = f"（原因：{reason}）" if reason else ""
                if level == "HARD":
                    hard.append(f"任课教师在该时段已设绝对禁排{suffix}")
                else:
                    soft.append(f"任课教师在该时段偏好避开{suffix}")

        # 1.5 V1.7 周期策略规则校验
        for pr in self.policy_rules:
            if pr.rule_type != 'FORBID_SCHEDULE':
                continue
            if pr.day_of_week not in (0, target_ts.day_of_week) or pr.period_index not in (0, target_ts.period_index):
                continue
            matched = (
                pr.target_type == 'GLOBAL'
                or (pr.target_type == 'TEACHER' and (pr.target_id is None or pr.target_id == task.teacher_id))
                or (pr.target_type == 'COHORT' and (pr.target_id is None or pr.target_id in (task.cohort_ids or [])))
                or (pr.target_type == 'CLASSROOM' and (pr.target_id is None or pr.target_id == target_room_id))
            )
            if matched:
                hard.append(f"违反周期禁排策略：{pr.remark or '该时段被设为禁排'}")

        if target_ts.is_evening:
            soft.append("目标时段为晚间课程（软约束扣分）")

        # 2. 固定教室独占、机房容量、软件环境标签、黑白名单与横向借用授权
        if getattr(target_room, 'usage_mode', 'FLOATING') == 'FIXED' and getattr(target_room, 'fixed_cohort_id', None) is not None:
            c_ids = list(task.cohort_ids or [])
            if not (len(c_ids) == 1 and c_ids[0] == target_room.fixed_cohort_id):
                hard.append(f'教室 {target_room.room_code} 为固定班级教室，禁止其他班级或合班课占用')
        if getattr(task, 'required_room_type', None) and target_room.room_type != task.required_room_type:
            hard.append(f'课程要求教室类型为 {task.required_room_type}，当前教室 {target_room.room_code} 类型为 {target_room.room_type}')
        if target_room.capacity < task.total_students:
            hard.append(f"教室 {target_room.room_code} 容量({target_room.capacity})小于合班人数({task.total_students})")

        req_tags = set(task.required_env_tags or [])
        room_tags = set(target_room.env_tags or [])
        if req_tags and not req_tags.issubset(room_tags):
            hard.append(f"机房 {target_room.room_code} 缺少必需软件环境：{sorted(req_tags - room_tags)}")

        allow_list = self.allow_rules.get(target_room_id, [])
        if allow_list:
            matched = any(
                (r.course_code and r.course_code == task.course_code)
                or (not r.course_code and r.course_category == task.course_category)
                for r in allow_list
            )
            if not matched:
                hard.append(f"机房 {target_room.room_code} 设有白名单限制，不允许当前课程进入")

        for r in self.deny_rules.get(target_room_id, []):
            if (r.course_code and r.course_code == task.course_code) or (
                not r.course_code and r.course_category == task.course_category
            ):
                hard.append(f"机房 {target_room.room_code} 黑名单禁止排入 {task.course_category} 类课程")
                break

        if target_room.sharing_policy != "PUBLIC_POOL":
            access = authorize_resource_access(
                self.db,
                requester_org_id=task.org_node_id,
                resource_owner_org_id=target_room.owner_org_id,
                resource_type="ROOM_POOL",
                semester_id=self.plan.semester_id,
            )
            if not access.allowed:
                hard.append(f"无权借用教室 {target_room.room_code}：{access.reason}")

        # 3. 分级公共课只读锁定校验
        task_cohorts = set(task.cohort_ids or [])
        for lk in self.locks_by_ts.get(target_ts_id, []):
            if not _weeks_overlap(detail.week_type, lk.week_type):
                continue
            if lk.classroom_id and lk.classroom_id == target_room_id:
                hard.append(f"教室 {target_room.room_code} 已被【{lk.course_name}】只读锁定占用")
            if lk.teacher_id and lk.teacher_id == task.teacher_id:
                hard.append(f"任课教师在该时段已被【{lk.course_name}】只读锁定占用")
            if lk.cohort_id and lk.cohort_id in task_cohorts:
                hard.append(f"合班行政班(id={lk.cohort_id})已被【{lk.course_name}】只读锁定占用")

        # 4. 同时间片教室、教师、行政班冲突校验（原生支持单双周复用）
        for other in self.details_by_ts.get(target_ts_id, []):
            if other.id == detail.id:
                continue
            other_task = self.task_by_id.get(other.task_id)
            other_mask = (
                getattr(other, 'week_mask', None)
                or (getattr(other_task, 'week_mask', None) if other_task else None)
                or build_week_mask(other_task.start_week if other_task else 1, other_task.end_week if other_task else 18, other.week_type)
            )
            if not masks_overlap(det_mask, other_mask):
                continue
            other_task = self.task_by_id.get(other.task_id)
            other_name = other_task.course_name if other_task else f"任务#{other.task_id}"
            if other.classroom_id == target_room_id:
                hard.append(f"教室 {target_room.room_code} 已被《{other_name}》占用")
            if other_task and other_task.teacher_id == task.teacher_id:
                hard.append(f"任课教师在该时段已有《{other_name}》授课安排（跨系/同系撞车）")
            if other_task:
                overlap_cohorts = task_cohorts & set(other_task.cohort_ids or [])
                if overlap_cohorts:
                    hard.append(f"行政班 {sorted(overlap_cohorts)} 在该时段已有《{other_name}》课程")

        # 5. 跨校区相邻节次通勤熔断校验（R3）
        target_campus = self.room_campus.get(target_room_id)
        if target_campus is not None:
            for adj_period in (target_ts.period_index - 1, target_ts.period_index + 1):
                if adj_period < 1:
                    continue
                for other_id, other_wt, other_campus in self.teacher_day_period_campuses.get(
                    (task.teacher_id, target_ts.day_of_week, adj_period), []
                ):
                    if other_id == detail.id:
                        continue
                    if not _weeks_overlap(detail.week_type, other_wt):
                        continue
                    if other_campus != target_campus:
                        c1_name = self.node_map[target_campus].node_name if target_campus in self.node_map else str(target_campus)
                        c2_name = self.node_map[other_campus].node_name if other_campus in self.node_map else str(other_campus)
                        hard.append(
                            f"跨校区通勤冲突：教师在周{target_ts.day_of_week}第{adj_period}大节位于【{c2_name}】，"
                            f"相邻节次无法及时赶往【{c1_name}】授课"
                        )
                        break

        return hard, soft


def check_drag_target(db: Session, req: DragCheckRequest) -> SlotLightResult:
    t0 = time.perf_counter()
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == req.plan_id).first()
    if plan is None:
        raise ValueError(f"排课方案 id={req.plan_id} 不存在")
    detail = (
        db.query(ScheduleDetail)
        .filter(ScheduleDetail.id == req.detail_id, ScheduleDetail.plan_id == req.plan_id)
        .first()
    )
    if detail is None:
        raise ValueError(f"课表明细 id={req.detail_id} 不存在")
    task = db.query(TeachingTask).filter(TeachingTask.id == detail.task_id).first()
    if task is None:
        raise ValueError(f"教学任务 id={detail.task_id} 不存在")

    snap = _PlanSnapshot(db, plan, scope=req.scope)
    hard, soft = snap.evaluate_slot(detail, task, req.target_timeslot_id, req.target_classroom_id)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    if hard:
        light, allowed = "RED", False
    elif soft:
        light, allowed = "YELLOW", True
    else:
        light, allowed = "GREEN", True

    return SlotLightResult(
        target_timeslot_id=req.target_timeslot_id,
        target_classroom_id=req.target_classroom_id,
        light=light,
        allowed=allowed,
        elapsed_ms=elapsed_ms,
        hard_conflicts=hard,
        soft_warnings=soft,
    )


def compute_matrix_lights(db: Session, req: MatrixLightsRequest) -> MatrixLightsResponse:
    """拖动开始瞬间，一次内存扫描返回所有时间片的红绿灯状态。"""
    t0 = time.perf_counter()
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == req.plan_id).first()
    if plan is None:
        raise ValueError(f"排课方案 id={req.plan_id} 不存在")
    detail = (
        db.query(ScheduleDetail)
        .filter(ScheduleDetail.id == req.detail_id, ScheduleDetail.plan_id == req.plan_id)
        .first()
    )
    if detail is None:
        raise ValueError(f"课表明细 id={req.detail_id} 不存在")
    task = db.query(TeachingTask).filter(TeachingTask.id == detail.task_id).first()
    if task is None:
        raise ValueError(f"教学任务 id={detail.task_id} 不存在")

    snap = _PlanSnapshot(db, plan, scope=req.scope)
    slots_out: Dict[int, SlotLightResult] = {}
    for ts_id in snap.ts_by_id:
        hard, soft = snap.evaluate_slot(detail, task, ts_id, req.target_classroom_id)
        if hard:
            light, allowed = "RED", False
        elif soft:
            light, allowed = "YELLOW", True
        else:
            light, allowed = "GREEN", True
        slots_out[ts_id] = SlotLightResult(
            target_timeslot_id=ts_id,
            target_classroom_id=req.target_classroom_id,
            light=light,
            allowed=allowed,
            elapsed_ms=0.0,
            hard_conflicts=hard,
            soft_warnings=soft,
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return MatrixLightsResponse(
        plan_id=req.plan_id,
        detail_id=req.detail_id,
        target_classroom_id=req.target_classroom_id,
        elapsed_ms=elapsed_ms,
        slots=slots_out,
    )


def apply_drag_move(db: Session, req: DragCheckRequest) -> SlotLightResult:
    result = check_drag_target(db, req)
    if not result.allowed:
        return result
    detail = db.query(ScheduleDetail).filter(ScheduleDetail.id == req.detail_id).first()
    if detail:
        detail.timeslot_id = req.target_timeslot_id
        detail.classroom_id = req.target_classroom_id
        detail.is_manual_adjusted = True
        db.commit()
    return result


def run_health_check(
    db: Session,
    semester_id: int,
    scope: str = "SCHOOL_WIDE",
    org_node_id: Optional[int] = None,
) -> HealthCheckReport:
    """全校 / 单院系一键体检：全局扫描跨系兼课撞车、教室冲突、班级冲突与跨校区相邻节次通勤违规。"""
    t0 = time.perf_counter()
    nodes = db.query(OrgNode).all()
    node_map = {n.id: n for n in nodes}
    ts_map = {t.id: t for t in db.query(Timeslot).all()}
    rooms = db.query(Classroom).all()
    room_map = {r.id: r for r in rooms}
    room_campus = {r.id: resolve_campus_boundary_id(node_map, r.owner_org_id) for r in rooms}

    plan_q = db.query(SchedulePlan).filter(SchedulePlan.semester_id == semester_id)
    if scope == "SINGLE_DEPT" and org_node_id is not None:
        plan_q = plan_q.filter(SchedulePlan.org_node_id == org_node_id)
    plans = plan_q.order_by(SchedulePlan.id.desc()).all()

    # 每个组织节点取最新一份方案进行全校总检
    latest_plan_by_org: Dict[int, SchedulePlan] = {}
    for p in plans:
        if p.org_node_id not in latest_plan_by_org:
            latest_plan_by_org[p.org_node_id] = p

    active_plan_ids = [p.id for p in latest_plan_by_org.values()]
    details = (
        db.query(ScheduleDetail).filter(ScheduleDetail.plan_id.in_(active_plan_ids)).all()
        if active_plan_ids
        else []
    )
    task_ids = {d.task_id for d in details}
    task_map = (
        {t.id: t for t in db.query(TeachingTask).filter(TeachingTask.id.in_(task_ids)).all()}
        if task_ids
        else {}
    )

    issues: List[HealthCheckIssue] = []

    # 1. 同时间片教室、教师、行政班碰撞扫描
    by_ts: Dict[int, List[ScheduleDetail]] = defaultdict(list)
    for d in details:
        by_ts[d.timeslot_id].append(d)

    for ts_id, items in by_ts.items():
        n = len(items)
        for i in range(n):
            for j in range(i + 1, n):
                d1, d2 = items[i], items[j]
                if not _weeks_overlap(d1.week_type, d2.week_type):
                    continue
                t1, t2 = task_map.get(d1.task_id), task_map.get(d2.task_id)
                if d1.classroom_id == d2.classroom_id:
                    rc = room_map[d1.classroom_id].room_code if d1.classroom_id in room_map else str(d1.classroom_id)
                    issues.append(
                        HealthCheckIssue(
                            issue_type="ROOM_CONFLICT",
                            message=f"时间片#{ts_id} 教室 {rc} 被《{t1.course_name if t1 else d1.task_id}》与《{t2.course_name if t2 else d2.task_id}》重复占用",
                            detail_ids=[d1.id, d2.id],
                        )
                    )
                if t1 and t2 and t1.teacher_id == t2.teacher_id:
                    issues.append(
                        HealthCheckIssue(
                            issue_type="TEACHER_CROSS_DEPT_CONFLICT",
                            message=f"时间片#{ts_id} 教师(id={t1.teacher_id})在《{t1.course_name}》与《{t2.course_name}》发生兼课撞车",
                            detail_ids=[d1.id, d2.id],
                        )
                    )
                if t1 and t2:
                    overlap_c = set(t1.cohort_ids or []) & set(t2.cohort_ids or [])
                    if overlap_c:
                        issues.append(
                            HealthCheckIssue(
                                issue_type="COHORT_CONFLICT",
                                message=f"时间片#{ts_id} 行政班 {sorted(overlap_c)} 存在课程重叠",
                                detail_ids=[d1.id, d2.id],
                            )
                        )

    # 2. 全周期教师时空序列扫描：跨校区相邻节次通勤熔断（R3）
    teacher_schedule: Dict[Tuple[int, int], List[Tuple[int, int, int, int]]] = defaultdict(list)
    for d in details:
        t = task_map.get(d.task_id)
        ts = ts_map.get(d.timeslot_id)
        c_id = room_campus.get(d.classroom_id)
        if t and ts and c_id is not None:
            teacher_schedule[(t.teacher_id, ts.day_of_week)].append(
                (ts.period_index, d.week_type, c_id, d.id)
            )

    seen_commute_pairs: Set[Tuple[int, int]] = set()
    for (teacher_id, day), entries in teacher_schedule.items():
        entries.sort(key=lambda x: x[0])
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                p1, w1, c1, id1 = entries[i]
                p2, w2, c2, id2 = entries[j]
                if p2 - p1 == 1 and c1 != c2 and _weeks_overlap(w1, w2):
                    pair_key = (min(id1, id2), max(id1, id2))
                    if pair_key not in seen_commute_pairs:
                        seen_commute_pairs.add(pair_key)
                        c1_name = node_map[c1].node_name if c1 in node_map else str(c1)
                        c2_name = node_map[c2].node_name if c2 in node_map else str(c2)
                        issues.append(
                            HealthCheckIssue(
                                issue_type="CROSS_CAMPUS_COMMUTE",
                                message=(
                                    f"跨校区通勤预警：教师(id={teacher_id})在周{day}第{p1}大节位于【{c1_name}】，"
                                    f"紧接着第{p2}大节排在【{c2_name}】，缺少物理在途通勤时间"
                                ),
                                detail_ids=[id1, id2],
                            )
                        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return HealthCheckReport(
        semester_id=semester_id,
        scope=scope,
        org_node_id=org_node_id,
        passed=(len(issues) == 0),
        total_checked_sessions=len(details),
        conflict_count=len(issues),
        elapsed_ms=elapsed_ms,
        issues=issues,
    )
