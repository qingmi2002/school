"""T1.4 验收门禁测试：硬约束零冲突、单双周复用、跨校区通勤熔断、两级松弛诊断及单系部百门课 10 秒压测。"""
from fastapi.testclient import TestClient

from app.main import app
from app.solver import (
    CourseScheduleSolver,
    SolverInput,
    SolverPublicLock,
    SolverRoom,
    SolverRoomRule,
    SolverTask,
    SolverTeacherUnavailable,
    SolverTimeslot,
)


def _make_standard_timeslots():
    slots = []
    idx = 1
    for day in range(1, 6):
        for period in range(1, 6):
            slots.append(
                SolverTimeslot(
                    id=idx,
                    day_of_week=day,
                    period_index=period,
                    period_name=f"周{day} 第{period}大节",
                    is_evening=(period == 5),
                )
            )
            idx += 1
    return slots


def test_odd_even_week_reuse_same_room_and_slot():
    # 仅有 1 个时间片 + 1 间机房，单周(1)和双周(2)两门课必须复用成功
    payload = SolverInput(
        timeslots=[SolverTimeslot(id=1, day_of_week=1, period_index=1, period_name="周一 1-2节")],
        rooms=[SolverRoom(id=10, room_code="LAB-402", owner_org_id=1, capacity=50, room_type="COMPUTER_LAB", env_tags=["Linux"])],
        tasks=[
            SolverTask(id=1, org_node_id=1, course_code="CS101", course_name="Linux实验A", course_category="LAB", teacher_id=101, cohort_ids=[1], weekly_sessions=1, week_type=1, total_students=40, required_env_tags=["Linux"]),
            SolverTask(id=2, org_node_id=1, course_code="CS102", course_name="Linux实验B", course_category="LAB", teacher_id=101, cohort_ids=[1], weekly_sessions=1, week_type=2, total_students=40, required_env_tags=["Linux"]),
        ],
    )
    result = CourseScheduleSolver(payload).solve()
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.stage_used == 1
    assert len(result.assignments) == 2
    assert {a.week_type for a in result.assignments} == {1, 2}


def test_hard_constraints_public_lock_blacklist_and_cross_campus_commute():
    # 同一天 1-2 节与 3-4 节分别位于主校区(100)和新校区(200)，同一教师不能连续跨校区排课
    slots = [
        SolverTimeslot(id=1, day_of_week=1, period_index=1),
        SolverTimeslot(id=2, day_of_week=1, period_index=2),
        SolverTimeslot(id=3, day_of_week=2, period_index=1),
    ]
    rooms = [
        SolverRoom(id=1, room_code="MAIN-101", owner_org_id=1, campus_boundary_id=100, capacity=60, room_type="NORMAL"),
        SolverRoom(id=2, room_code="NEW-LAB1", owner_org_id=2, campus_boundary_id=200, capacity=60, room_type="COMPUTER_LAB", env_tags=["GPU"]),
    ]
    tasks = [
        SolverTask(id=1, org_node_id=1, course_code="TH101", course_name="离散数学", course_category="THEORY", teacher_id=501, cohort_ids=[1], weekly_sessions=1, total_students=50),
        SolverTask(id=2, org_node_id=2, course_code="AI201", course_name="深度学习实验", course_category="LAB", teacher_id=501, cohort_ids=[2], weekly_sessions=1, total_students=50, required_env_tags=["GPU"]),
    ]
    payload = SolverInput(
        timeslots=slots,
        rooms=rooms,
        tasks=tasks,
        public_locks=[SolverPublicLock(timeslot_id=1, classroom_id=2, course_name="公共AI通识")],
        room_rules=[SolverRoomRule(classroom_id=2, course_category="THEORY", rule_type="DENY")],
        teacher_unavailable=[SolverTeacherUnavailable(teacher_id=501, timeslot_id=3, constraint_level="SOFT")],
    )
    result = CourseScheduleSolver(payload).solve()
    assert result.status in ("OPTIMAL", "FEASIBLE")
    by_task = {a.task_id: a for a in result.assignments}
    # 理论课不得进入黑名单机房2
    assert by_task[1].classroom_id == 1
    # 实验课必须进带 GPU 标签的机房2，且避让时间片1的公共课锁定
    assert by_task[2].classroom_id == 2
    assert by_task[2].timeslot_id != 1
    # 验证跨校区未在周一相邻节次(1与2)连续排课
    assert not ({by_task[1].timeslot_id, by_task[2].timeslot_id} == {1, 2})


def test_two_stage_slack_diagnostics_when_infeasible():
    # 人为制造无解：任务2需要 GPU 标签但无任何 GPU 机房
    payload = SolverInput(
        timeslots=[SolverTimeslot(id=1, day_of_week=1, period_index=1)],
        rooms=[SolverRoom(id=1, room_code="N-101", owner_org_id=1, capacity=60, room_type="NORMAL", env_tags=[])],
        tasks=[
            SolverTask(id=1, org_node_id=1, course_code="CS101", course_name="高等数学", course_category="THEORY", teacher_id=1, cohort_ids=[1], weekly_sessions=1, total_students=40),
            SolverTask(id=2, org_node_id=1, course_code="CS999", course_name="GPU集群实战", course_category="LAB", teacher_id=2, cohort_ids=[2], weekly_sessions=1, total_students=40, required_env_tags=["GPU"]),
        ],
    )
    result = CourseScheduleSolver(payload).solve()
    assert result.status == "PARTIAL_RELAXED"
    assert result.stage_used == 2
    assert len(result.assignments) == 1
    assert result.assignments[0].task_id == 1
    assert len(result.unscheduled_diagnostics) == 1
    assert result.unscheduled_diagnostics[0].task_id == 2
    assert any("GPU" in r for r in result.unscheduled_diagnostics[0].reasons)


def test_m1_gate_100_courses_within_10_seconds_zero_conflict():
    """M1 验收门禁：单系部 100 门课程 10 秒内算出 100% 无冲突课表。"""
    slots = _make_standard_timeslots()  # 25 个标准时间片
    rooms = [
        SolverRoom(
            id=i,
            room_code=f"R-{i:03d}",
            owner_org_id=1,
            campus_boundary_id=1,
            capacity=80,
            room_type="COMPUTER_LAB" if i <= 6 else "NORMAL",
            env_tags=["Linux", "Python"] if i <= 6 else [],
        )
        for i in range(1, 16)  # 15 间教室（6机房 + 9普通教室）
    ]
    tasks = [
        SolverTask(
            id=i,
            org_node_id=1,
            course_code=f"CS{i:03d}",
            course_name=f"专业课_{i}",
            course_category="LAB" if i % 4 == 0 else "THEORY",
            teacher_id=(i % 20) + 1,  # 20 位教师，每人 5 门课
            cohort_ids=[(i % 15) + 1],  # 15 个行政班
            weekly_sessions=1,
            week_type=0,
            total_students=45,
            required_env_tags=["Python"] if i % 4 == 0 else [],
        )
        for i in range(1, 101)  # 100 门课程
    ]
    payload = SolverInput(
        timeslots=slots,
        rooms=rooms,
        tasks=tasks,
        time_limit_seconds=10.0,
    )
    result = CourseScheduleSolver(payload).solve()
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.stage_used == 1
    assert result.solve_seconds < 10.0
    assert len(result.assignments) == 100
    assert len(result.unscheduled_diagnostics) == 0

    # 二次独立校验：零教室、零教师、零班级冲突
    room_seen, teacher_seen, cohort_seen = set(), set(), set()
    task_map = {t.id: t for t in tasks}
    for a in result.assignments:
        t = task_map[a.task_id]
        assert (a.classroom_id, a.timeslot_id) not in room_seen
        room_seen.add((a.classroom_id, a.timeslot_id))
        assert (t.teacher_id, a.timeslot_id) not in teacher_seen
        teacher_seen.add((t.teacher_id, a.timeslot_id))
        for cid in t.cohort_ids:
            assert (cid, a.timeslot_id) not in cohort_seen
            cohort_seen.add((cid, a.timeslot_id))


def test_solver_dry_run_api():
    client = TestClient(app)
    resp = client.post(
        "/api/v1/solver/dry-run",
        json={
            "timeslots": [{"id": 1, "day_of_week": 1, "period_index": 1}],
            "rooms": [{"id": 1, "room_code": "A101", "owner_org_id": 1, "capacity": 50}],
            "tasks": [{"id": 1, "org_node_id": 1, "course_code": "C1", "course_name": "算法", "teacher_id": 1, "cohort_ids": [1], "weekly_sessions": 1, "total_students": 30}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("OPTIMAL", "FEASIBLE")
    assert len(body["assignments"]) == 1
