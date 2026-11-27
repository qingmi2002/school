"""V1.6 验收测试：单课程学期总课时自动顺延实训周 + 6大求解器优化（周期规则、精确周次分段复用、已锁课避让、隔天/连堂、日均衡、自有教室优先）。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.week_mask import build_week_mask, fit_week_mask_to_hours, mask_to_label, weeks_to_mask
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    Classroom,
    CohortWeekPlan,
    OrgNode,
    ScheduleDetail,
    SchedulePlan,
    SchedulePolicyRule,
    Semester,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org import apply_org_preset
from app.solver.cp_sat_engine import CourseScheduleSolver
from app.solver.schemas import SolverInput, SolverPolicyRule, SolverRoom, SolverTask, SolverTimeslot


@pytest.fixture()
def client_and_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()

    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    yield client, db
    app.dependency_overrides.clear()
    db.close()


def test_total_hours_auto_skips_practicum_and_fits_exact_weeks():
    # 32学时、每周2大节(4学时/周)需8周；第5-6周整周实训跳过 -> 自动顺延到 1-4,7-10周
    blocked = weeks_to_mask([5, 6])
    eff_mask, eff_weeks, actual_hours = fit_week_mask_to_hours(1, 18, 0, blocked, 32, 2, hours_per_session=2)
    assert eff_weeks == 8
    assert actual_hours == 32
    assert mask_to_label(eff_mask) == "1-4,7-10周"


def test_solver_six_optimizations_segmented_reuse_policy_and_own_room_priority():
    # 仅 1 个时间片 + 2 间教室（1间本院自有、1间兄弟院借用）
    # 任务A(1-8周)与任务B(9-16周)同班同师，验证精确 week_mask 允许同时间片同教室无缝复用，且优先选本院自有教室
    slots = [
        SolverTimeslot(id=1, day_of_week=1, period_index=1, period_name="周一1-2"),
        SolverTimeslot(id=2, day_of_week=1, period_index=2, period_name="周一3-4"),
    ]
    rooms = [
        SolverRoom(id=10, room_code="OWN-101", owner_org_id=1, capacity=60, room_type="NORMAL", sharing_policy="EXCLUSIVE"),
        SolverRoom(id=11, room_code="BORROW-201", owner_org_id=2, capacity=60, room_type="NORMAL", sharing_policy="IDLE_BORROW"),
    ]
    tasks = [
        SolverTask(
            id=1, org_node_id=1, course_code="C1", course_name="前半学期课",
            teacher_id=100, cohort_ids=[1], weekly_sessions=1, week_type=0,
            week_mask=build_week_mask(1, 8, 0), total_students=40,
        ),
        SolverTask(
            id=2, org_node_id=1, course_code="C2", course_name="后半学期课",
            teacher_id=100, cohort_ids=[1], weekly_sessions=1, week_type=0,
            week_mask=build_week_mask(9, 16, 0), total_students=40,
        ),
    ]
    # 周期规则禁止周一1-2节全校排课 -> 两门课必须都落入周一3-4节且同复用本院自有教室 OWN-101
    rules = [
        SolverPolicyRule(target_type="GLOBAL", rule_type="FORBID_SCHEDULE", day_of_week=1, period_index=1),
    ]
    res = CourseScheduleSolver(SolverInput(timeslots=slots, rooms=rooms, tasks=tasks, policy_rules=rules)).solve()
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert len(res.assignments) == 2
    assert all(a.timeslot_id == 2 for a in res.assignments)
    assert all(a.classroom_id == 10 for a in res.assignments)


def test_v1_6_api_total_hours_and_locked_task_avoidance(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    sem = Semester(code="2026-2027-2", name="2026春", total_weeks=18, is_current=True)
    db.add(sem)
    db.flush()

    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一1-2")
    ts2 = Timeslot(org_node_id=None, day_of_week=3, period_index=1, period_name="周三1-2")
    c1 = StudentCohort(org_node_id=dept.id, cohort_code="SE2401", cohort_name="软件2401", student_count=40, grade_year=2024)
    r1 = Classroom(room_code="R-101", building="主楼", owner_org_id=dept.id, capacity=60, room_type="NORMAL", usage_mode="FLOATING")
    t1 = SysUser(username="t1", real_name="张老师", org_node_id=dept.id, role_code="TEACHER", password_hash="x")
    db.add_all([ts1, ts2, c1, r1, t1])
    db.flush()

    # 设定软件2401第3-4周整周实训
    db.add_all([
        CohortWeekPlan(semester_id=sem.id, cohort_id=c1.id, week_no=3, week_mode="PRACTICUM", block_course_name="实训"),
        CohortWeekPlan(semester_id=sem.id, cohort_id=c1.id, week_no=4, week_mode="PRACTICUM", block_course_name="实训"),
    ])
    # 周期规则：不限制 ts2
    db.add(SchedulePolicyRule(semester_id=sem.id, target_type="GLOBAL", rule_type="PREFER_SCHEDULE", day_of_week=3, period_index=1))
    db.commit()

    # 建课（默认24学时）并创建任务 -> 24学时、周2节(4学时/周)=6有效周，跳过3-4周 -> 1-2,5-8周
    rc = client.post("/api/v1/curriculum/courses", json={
        "owner_org_id": dept.id, "course_code": "DB101", "course_name": "数据库原理",
        "course_category": "THEORY", "required_room_type": "NORMAL",
        "default_weekly_sessions": 2, "default_total_hours": 24, "allow_combined": True,
    })
    assert rc.status_code == 200
    rt = client.post("/api/v1/curriculum/tasks", json={
        "semester_id": sem.id, "course_id": rc.json()["id"], "teacher_id": t1.id, "cohort_ids": [c1.id],
    })
    assert rt.status_code == 200
    tdata = rt.json()
    assert tdata["total_hours"] == 24
    assert tdata["planned_actual_hours"] == 24
    assert tdata["effective_weeks_label"] == "1-2,5-8周"

    # 验证已锁定任务在局部重排时自动占坑避让：建一条已锁定任务占住 ts1，再排一条未锁定任务必须自动避开 ts1 落入 ts2
    locked_task = TeachingTask(
        semester_id=sem.id, org_node_id=dept.id, course_code="LOCK1", course_name="已锁课",
        course_category="THEORY", teacher_id=t1.id, cohort_ids=[c1.id], weekly_sessions=1,
        week_type=0, total_students=40, is_locked=True,
    )
    db.add(locked_task)
    db.flush()
    old_plan = SchedulePlan(semester_id=sem.id, org_node_id=dept.id, plan_name="旧方案", version_tag="V0", run_mode="SINGLE_DEPT")
    db.add(old_plan)
    db.flush()
    db.add(ScheduleDetail(plan_id=old_plan.id, task_id=locked_task.id, timeslot_id=ts1.id, classroom_id=r1.id, week_type=0))
    # 删除刚建的 2 节任务，换 1 节未锁定任务测试避让 ts1
    db.query(TeachingTask).filter(TeachingTask.id == tdata["id"]).delete()
    free_task = TeachingTask(
        semester_id=sem.id, org_node_id=dept.id, course_code="FREE1", course_name="待重排课",
        course_category="THEORY", teacher_id=t1.id, cohort_ids=[c1.id], weekly_sessions=1,
        week_type=0, total_students=40, is_locked=False,
    )
    db.add(free_task)
    db.commit()

    res = client.post("/api/v1/solver/one-click", json={"semester_id": sem.id, "org_node_id": dept.id})
    assert res.status_code == 200
    assert res.json()["scheduled_count"] == 1
    new_det = db.query(ScheduleDetail).filter(ScheduleDetail.plan_id == res.json()["plan_id"]).first()
    assert new_det.timeslot_id == ts2.id
