"""
T1.4 核心排课求解引擎 — Google OR-Tools (CP-SAT)
特性：
1. 硬约束零冲突（时空唯一、单双周复用、公共课锁定避让、教师硬禁排、机房黑白名单与软环境、容量、跨校区相邻节次通勤熔断）。
2. 软约束综合打分（避开晚间、避开教师软禁排、教学节奏间隔分布、专业机房与容量紧凑匹配）。
3. 两级求解机制（R1 风险兜底）：第一级严格 100% 排满；无解时自动切换第二级引入松弛变量定位最小冲突子集并生成中文诊断。
"""
from collections import defaultdict
import time
from typing import Dict, List, Set, Tuple

from ortools.sat.python import cp_model

from app.solver.schemas import (
    ScheduledAssignment,
    SolverInput,
    SolverResult,
    SolverRoom,
    SolverTask,
    UnscheduledDiagnostic,
)


def _weeks_overlap(w1: int, w2: int) -> bool:
    """判断两个单双周属性是否重叠：0=全周, 1=单周, 2=双周。单周(1)与双周(2)不重叠。"""
    return w1 == 0 or w2 == 0 or w1 == w2


class CourseScheduleSolver:
    """工业级确定性排课求解器（CP-SAT）"""

    def __init__(self, data: SolverInput):
        self.data = data
        self.timeslot_by_id = {ts.id: ts for ts in data.timeslots}
        self.room_by_id = {r.id: r for r in data.rooms}
        self.task_by_id = {t.id: t for t in data.tasks}

        # 预处理规则索引
        self.hard_teacher_unavail: Set[Tuple[int, int]] = set()
        self.soft_teacher_unavail: Set[Tuple[int, int]] = set()
        for item in data.teacher_unavailable:
            key = (item.teacher_id, item.timeslot_id)
            if item.constraint_level == "HARD":
                self.hard_teacher_unavail.add(key)
            else:
                self.soft_teacher_unavail.add(key)

        self.allow_rules_by_room: Dict[int, List] = defaultdict(list)
        self.deny_rules_by_room: Dict[int, List] = defaultdict(list)
        for rule in data.room_rules:
            if rule.rule_type == "ALLOW":
                self.allow_rules_by_room[rule.classroom_id].append(rule)
            else:
                self.deny_rules_by_room[rule.classroom_id].append(rule)

        # 公共课锁定索引
        self.locked_cohort_slots: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        self.locked_room_slots: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        self.locked_teacher_slots: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for lock in data.public_locks:
            if lock.cohort_id is not None:
                self.locked_cohort_slots[(lock.cohort_id, lock.timeslot_id)].append(lock.week_type)
            if lock.classroom_id is not None:
                self.locked_room_slots[(lock.classroom_id, lock.timeslot_id)].append(lock.week_type)
            if lock.teacher_id is not None:
                self.locked_teacher_slots[(lock.teacher_id, lock.timeslot_id)].append(lock.week_type)

    def _is_room_compatible(self, task: SolverTask, room: SolverRoom) -> Tuple[bool, str]:
        # V1.5 硬约束1：固定班级教室绝对独占（其他班级或合班任务禁止占用）
        if room.usage_mode == "FIXED" and room.fixed_cohort_id is not None:
            if not (len(task.cohort_ids) == 1 and task.cohort_ids[0] == room.fixed_cohort_id):
                return False, "fixed_room_exclusive"

        # V1.5 硬约束2：显式指定教室类型硬匹配（机房/普通教室/阶梯教室分离）
        if task.required_room_type:
            if room.room_type != task.required_room_type:
                return False, "room_type"

        if room.capacity < task.total_students:
            return False, "capacity"

        if task.required_env_tags:
            room_tags = set(room.env_tags)
            if not set(task.required_env_tags).issubset(room_tags):
                return False, "env_tags"

        # 机房白名单校验（若该机房存在白名单，则仅允许匹配规则的课程进入）
        allow_rules = self.allow_rules_by_room.get(room.id, [])
        if allow_rules:
            matched = any(
                (r.course_code and r.course_code == task.course_code)
                or (not r.course_code and r.course_category and r.course_category == task.course_category)
                for r in allow_rules
            )
            if not matched:
                return False, "whitelist"

        # 机房黑名单校验
        deny_rules = self.deny_rules_by_room.get(room.id, [])
        for r in deny_rules:
            if r.course_code and r.course_code == task.course_code:
                return False, "blacklist"
            if not r.course_code and r.course_category and r.course_category == task.course_category:
                return False, "blacklist"

        return True, ""

    def _is_slot_allowed_for_task(self, task: SolverTask, ts_id: int) -> Tuple[bool, str]:
        if (task.teacher_id, ts_id) in self.hard_teacher_unavail:
            return False, "teacher_hard_unavail"

        for w in self.locked_teacher_slots.get((task.teacher_id, ts_id), []):
            if _weeks_overlap(task.week_type, w):
                return False, "public_lock_teacher"

        for cid in task.cohort_ids:
            for w in self.locked_cohort_slots.get((cid, ts_id), []):
                if _weeks_overlap(task.week_type, w):
                    return False, "public_lock_cohort"

        return True, ""

    def _is_room_slot_free_of_locks(self, task: SolverTask, room_id: int, ts_id: int) -> bool:
        for w in self.locked_room_slots.get((room_id, ts_id), []):
            if _weeks_overlap(task.week_type, w):
                return False
        return True

    def _build_candidates(self) -> Tuple[Dict[int, List[Tuple[int, int]]], Dict[int, List[str]]]:
        """预剪枝生成每门任务的合法 (timeslot_id, room_id) 候选域，并记录空域诊断原因。"""
        candidates: Dict[int, List[Tuple[int, int]]] = {}
        pre_diagnostics: Dict[int, List[str]] = defaultdict(list)

        for task in self.data.tasks:
            valid_rooms = []
            room_fail_reasons: Set[str] = set()
            for room in self.data.rooms:
                ok, reason = self._is_room_compatible(task, room)
                if ok:
                    valid_rooms.append(room)
                else:
                    room_fail_reasons.add(reason)

            valid_slots = []
            slot_fail_reasons: Set[str] = set()
            for ts in self.data.timeslots:
                ok, reason = self._is_slot_allowed_for_task(task, ts.id)
                if ok:
                    valid_slots.append(ts)
                else:
                    slot_fail_reasons.add(reason)

            pairs: List[Tuple[int, int]] = []
            for ts in valid_slots:
                for room in valid_rooms:
                    if self._is_room_slot_free_of_locks(task, room.id, ts.id):
                        pairs.append((ts.id, room.id))

            candidates[task.id] = pairs

            if not valid_rooms:
                if "capacity" in room_fail_reasons:
                    pre_diagnostics[task.id].append(f"无满足人数容量({task.total_students}人)的可用教室/机房")
                if "env_tags" in room_fail_reasons:
                    pre_diagnostics[task.id].append(f"无满足软件环境标签 {task.required_env_tags} 的机房")
                if "whitelist" in room_fail_reasons or "blacklist" in room_fail_reasons:
                    pre_diagnostics[task.id].append("受机房黑白名单规则限制，无合规场地")
            if len(valid_slots) < task.weekly_sessions:
                if "teacher_hard_unavail" in slot_fail_reasons:
                    pre_diagnostics[task.id].append("教师硬性禁排时段过多，剩余可用时间片不足")
                if "public_lock_cohort" in slot_fail_reasons or "public_lock_teacher" in slot_fail_reasons:
                    pre_diagnostics[task.id].append("与校级/上级公共课锁定时间片大面积重叠")
            elif len(pairs) < task.weekly_sessions and not pre_diagnostics[task.id]:
                pre_diagnostics[task.id].append("候选教室在可用时段均被公共课锁定占用")

        return candidates, pre_diagnostics

    def _pair_score(self, task: SolverTask, ts_id: int, room_id: int) -> int:
        """计算单个 (task, timeslot, room) 分配的软约束静态得分。"""
        score = 100
        ts = self.timeslot_by_id[ts_id]
        room = self.room_by_id[room_id]

        if ts.is_evening:
            score -= 15
        if (task.teacher_id, ts_id) in self.soft_teacher_unavail:
            score -= 25 * max(1, task.teacher_priority)

        # V1.5 固定班普通理论课优先落在自己的固定教室
        if (
            room.usage_mode == "FIXED"
            and room.fixed_cohort_id is not None
            and len(task.cohort_ids) == 1
            and task.cohort_ids[0] == room.fixed_cohort_id
            and task.course_category == "THEORY"
        ):
            score += 18

        # 场地类型适配加分
        is_lab_room = room.room_type in ("COMPUTER_LAB", "NETWORK_LAB", "TRAINING_ROOM")
        if task.course_category == "LAB" and is_lab_room:
            score += 12
        elif task.course_category == "THEORY" and room.room_type == "NORMAL":
            score += 10
        elif task.course_category == "THEORY" and is_lab_room:
            score -= 8

        # 容量紧凑度（减少大教室装小班的浪费）
        waste_ratio = (room.capacity - task.total_students) / max(room.capacity, 1)
        if waste_ratio <= 0.25:
            score += 6
        elif waste_ratio >= 0.6:
            score -= 4

        return score

    def _solve_once(
        self,
        candidates: Dict[int, List[Tuple[int, int]]],
        pre_diagnostics: Dict[int, List[str]],
        relaxed: bool,
    ) -> Tuple[int, cp_model.CpSolver, dict, dict]:
        model = cp_model.CpModel()
        x: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
        slack: Dict[int, cp_model.IntVar] = {}

        # 按资源分桶：分别维护单周占用(week_type in {0,1})与双周占用(week_type in {0,2})
        room_odd = defaultdict(list)
        room_even = defaultdict(list)
        teacher_odd = defaultdict(list)
        teacher_even = defaultdict(list)
        cohort_odd = defaultdict(list)
        cohort_even = defaultdict(list)

        task_slot_vars: Dict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
        task_day_vars: Dict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
        teacher_slot_campus: Dict[Tuple[int, int, int], List[cp_model.IntVar]] = defaultdict(list)

        objective_terms = []

        for task in self.data.tasks:
            pairs = candidates[task.id]
            task_vars = []
            for ts_id, room_id in pairs:
                var = model.NewBoolVar(f"x_t{task.id}_s{ts_id}_r{room_id}")
                x[(task.id, ts_id, room_id)] = var
                task_vars.append(var)

                task_slot_vars[(task.id, ts_id)].append(var)
                day = self.timeslot_by_id[ts_id].day_of_week
                task_day_vars[(task.id, day)].append(var)

                # 单双周复用约束分桶
                if task.week_type in (0, 1):
                    room_odd[(room_id, ts_id)].append(var)
                    teacher_odd[(task.teacher_id, ts_id)].append(var)
                    for cid in task.cohort_ids:
                        cohort_odd[(cid, ts_id)].append(var)
                if task.week_type in (0, 2):
                    room_even[(room_id, ts_id)].append(var)
                    teacher_even[(task.teacher_id, ts_id)].append(var)
                    for cid in task.cohort_ids:
                        cohort_even[(cid, ts_id)].append(var)

                # 跨校区通勤追踪（仅当教室已溯源到校区边界时）
                campus_id = self.room_by_id[room_id].campus_boundary_id
                if campus_id is not None:
                    teacher_slot_campus[(task.teacher_id, ts_id, campus_id)].append(var)

                objective_terms.append(self._pair_score(task, ts_id, room_id) * var)

            # 1. 课时足额约束（严格 vs 松弛）
            if relaxed:
                s_var = model.NewIntVar(0, task.weekly_sessions, f"slack_t{task.id}")
                slack[task.id] = s_var
                model.Add(sum(task_vars) + s_var == task.weekly_sessions)
                # 极大惩罚，保证优先尽量排满所有课程
                objective_terms.append(-100000 * s_var)
            else:
                model.Add(sum(task_vars) == task.weekly_sessions)

            # 2. 同一任务在同一时间片最多排 1 间教室
            for (tid, _ts_id), vlist in list(task_slot_vars.items()):
                if tid == task.id and len(vlist) > 1:
                    model.Add(sum(vlist) <= 1)

            # 3. 同一任务尽量不排在同一天多次（当天数足够时作为硬约束）
            available_days = {self.timeslot_by_id[ts_id].day_of_week for ts_id, _ in pairs}
            if len(available_days) >= task.weekly_sessions:
                for d in available_days:
                    vlist = task_day_vars.get((task.id, d), [])
                    if len(vlist) > 1:
                        model.Add(sum(vlist) <= 1)

        # 4. 教室、教师、行政班单双周唯一性硬约束
        for bucket in (room_odd, room_even, teacher_odd, teacher_even, cohort_odd, cohort_even):
            for vlist in bucket.values():
                if len(vlist) > 1:
                    model.Add(sum(vlist) <= 1)

        # 5. 跨校区相邻节次通勤熔断硬约束
        slot_by_day_period: Dict[Tuple[int, int], int] = {
            (ts.day_of_week, ts.period_index): ts.id for ts in self.data.timeslots
        }
        all_teachers = {t.teacher_id for t in self.data.tasks}
        all_campuses = {r.campus_boundary_id for r in self.data.rooms if r.campus_boundary_id is not None}

        if len(all_campuses) >= 2:
            for teacher_id in all_teachers:
                for (day, period), ts_id_1 in slot_by_day_period.items():
                    ts_id_2 = slot_by_day_period.get((day, period + 1))
                    if ts_id_2 is None:
                        continue
                    for c1 in all_campuses:
                        vars_c1 = teacher_slot_campus.get((teacher_id, ts_id_1, c1), [])
                        if not vars_c1:
                            continue
                        for c2 in all_campuses:
                            if c1 == c2:
                                continue
                            vars_c2 = teacher_slot_campus.get((teacher_id, ts_id_2, c2), [])
                            if not vars_c2:
                                continue
                            model.Add(sum(vars_c1) + sum(vars_c2) <= 1)

        # 6. 软约束：同课程相邻两天连排扣分（鼓励周一+周四间隔分布）
        for task in self.data.tasks:
            if task.weekly_sessions < 2:
                continue
            for day in range(1, 7):
                v1 = task_day_vars.get((task.id, day), [])
                v2 = task_day_vars.get((task.id, day + 1), [])
                if v1 and v2:
                    adj = model.NewBoolVar(f"adj_t{task.id}_d{day}")
                    model.Add(sum(v1) + sum(v2) - 1 <= adj)
                    objective_terms.append(-10 * adj)

        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.data.time_limit_seconds
        solver.parameters.num_search_workers = self.data.num_search_workers
        status = solver.Solve(model)
        return status, solver, x, slack

    def solve(self) -> SolverResult:
        t0 = time.perf_counter()
        candidates, pre_diagnostics = self._build_candidates()

        # 快速预检：若有任务连基础候选域都不足，直接进入第二级松弛诊断，省去无效搜索
        has_empty_domain = any(len(candidates[t.id]) < t.weekly_sessions for t in self.data.tasks)

        stage_used = 1
        status = cp_model.INFEASIBLE
        solver = None
        x = {}
        slack = {}

        if not has_empty_domain:
            status, solver, x, slack = self._solve_once(candidates, pre_diagnostics, relaxed=False)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            stage_used = 2
            status, solver, x, slack = self._solve_once(candidates, pre_diagnostics, relaxed=True)

        elapsed = round(time.perf_counter() - t0, 4)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return SolverResult(
                status="INFEASIBLE",
                stage_used=stage_used,
                solve_seconds=elapsed,
                fitness_score=0.0,
                assignments=[],
                unscheduled_diagnostics=[
                    UnscheduledDiagnostic(
                        task_id=t.id,
                        course_code=t.course_code,
                        course_name=t.course_name,
                        required_sessions=t.weekly_sessions,
                        scheduled_sessions=0,
                        reasons=pre_diagnostics.get(t.id) or ["求解超时或全局资源极度紧张"],
                    )
                    for t in self.data.tasks
                ],
                stats={"total_tasks": len(self.data.tasks), "scheduled_sessions": 0},
            )

        assignments: List[ScheduledAssignment] = []
        scheduled_count_by_task: Dict[int, int] = defaultdict(int)
        for (tid, ts_id, room_id), var in x.items():
            if solver.Value(var) == 1:
                task = self.task_by_id[tid]
                assignments.append(
                    ScheduledAssignment(
                        task_id=tid,
                        timeslot_id=ts_id,
                        classroom_id=room_id,
                        week_type=task.week_type,
                    )
                )
                scheduled_count_by_task[tid] += 1

        diagnostics: List[UnscheduledDiagnostic] = []
        for task in self.data.tasks:
            got = scheduled_count_by_task.get(task.id, 0)
            if got < task.weekly_sessions:
                reasons = list(pre_diagnostics.get(task.id, []))
                if not reasons:
                    reasons.append("可用时段内教师、合班或机房资源与其他课程发生全局竞争冲突")
                diagnostics.append(
                    UnscheduledDiagnostic(
                        task_id=task.id,
                        course_code=task.course_code,
                        course_name=task.course_name,
                        required_sessions=task.weekly_sessions,
                        scheduled_sessions=got,
                        reasons=reasons,
                    )
                )

        if diagnostics:
            final_status = "PARTIAL_RELAXED"
        else:
            final_status = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"

        return SolverResult(
            status=final_status,
            stage_used=stage_used,
            solve_seconds=elapsed,
            fitness_score=float(solver.ObjectiveValue()),
            assignments=assignments,
            unscheduled_diagnostics=diagnostics,
            stats={
                "total_tasks": len(self.data.tasks),
                "total_required_sessions": sum(t.weekly_sessions for t in self.data.tasks),
                "scheduled_sessions": len(assignments),
                "unscheduled_tasks": len(diagnostics),
            },
        )
