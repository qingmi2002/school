"""V1.9 生产定稿验收测试：防重置超管越权、跨院系资源/排课 IDOR 拦截、局部重排继承已锁课程、实训周变更联动重算总课时周次、师生端仅看已发布正式课表。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token, hash_password
from app.core.config import settings
from app.core.week_mask import mask_to_label
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    Classroom,
    OrgNode,
    ScheduleDetail,
    SchedulePlan,
    Semester,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org import apply_org_preset


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


def test_v1_9_reset_password_privesc_and_cross_dept_idor(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept_a = db.query(OrgNode).first()
    dept_b = OrgNode(
        parent_id=dept_a.parent_id, node_code="DEPT_B", node_name="外语系",
        node_type_code=dept_a.node_type_code, tree_path="/88/", depth=dept_a.depth,
    )
    db.add(dept_b)
    db.flush()

    super_admin = SysUser(username="root", real_name="总管", org_node_id=dept_a.id, role_code="SUPER_ADMIN", password_hash=hash_password("Admin@2026"))
    dept_admin_a = SysUser(username="da", real_name="A系管理员", org_node_id=dept_a.id, role_code="DEPT_SCHEDULER", password_hash=hash_password("123456"))
    teacher_b = SysUser(username="tb", real_name="B系教师", org_node_id=dept_b.id, role_code="TEACHER", password_hash=hash_password("123456"))
    db.add_all([super_admin, dept_admin_a, teacher_b])
    db.commit()

    tok_da = create_access_token(dept_admin_a.id, dept_admin_a.username, dept_admin_a.role_code, dept_a.id)
    settings.ENFORCE_API_AUTH = True
    try:
        # 1. 系级管理员禁止重置超管密码 -> 403
        r1 = client.post("/api/v1/auth/reset-password", headers={"Authorization": f"Bearer {tok_da}"}, json={"user_id": super_admin.id, "new_password": "hacked123"})
        assert r1.status_code == 403
        # 2. 系级管理员禁止重置外系教师密码 -> 403
        r2 = client.post("/api/v1/auth/reset-password", headers={"Authorization": f"Bearer {tok_da}"}, json={"user_id": teacher_b.id, "new_password": "hacked123"})
        assert r2.status_code == 403
        # 3. 系级管理员禁止给外系建教师 -> 403
        r3 = client.post("/api/v1/resources/teachers", headers={"Authorization": f"Bearer {tok_da}"}, json={"username": "evil_t", "real_name": "越权师", "org_node_id": dept_b.id})
        assert r3.status_code == 403
    finally:
        settings.ENFORCE_API_AUTH = False


def test_v1_9_locked_inheritance_week_plan_refit_and_draft_isolation(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    sem = Semester(code="2026-2", name="2026春", total_weeks=18, is_current=True)
    db.add(sem)
    db.flush()

    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一1-2")
    ts2 = Timeslot(org_node_id=None, day_of_week=2, period_index=1, period_name="周二1-2")
    c1 = StudentCohort(org_node_id=dept.id, cohort_code="SE2401", cohort_name="软件2401", student_count=40, grade_year=2024)
    r1 = Classroom(room_code="R-101", building="主楼", owner_org_id=dept.id, capacity=60, room_type="NORMAL", usage_mode="FLOATING")
    t1 = SysUser(username="t1", real_name="张老师", org_node_id=dept.id, role_code="TEACHER", password_hash=hash_password("123456"))
    stu = SysUser(username="s1", real_name="学生甲", org_node_id=dept.id, cohort_id=None, role_code="STUDENT", password_hash=hash_password("123456"))
    db.add_all([ts1, ts2, c1, r1, t1, stu])
    db.flush()
    stu.cohort_id = c1.id

    # 1. 先创建一门 24 学时、周 2 节(6周) 的任务，初始为 1-6 周；再把第 3-4 周改为整周实训 -> 自动联动顺延为 1-2,5-8 周
    task_free = TeachingTask(
        semester_id=sem.id, org_node_id=dept.id, course_code="DB1", course_name="数据库",
        course_category="THEORY", teacher_id=t1.id, cohort_ids=[c1.id], weekly_sessions=1,
        total_hours=12, week_type=0, start_week=1, end_week=18, total_students=40, is_locked=False,
    )
    task_locked = TeachingTask(
        semester_id=sem.id, org_node_id=dept.id, course_code="LK1", course_name="已锁核心课",
        course_category="THEORY", teacher_id=t1.id, cohort_ids=[c1.id], weekly_sessions=1,
        week_type=0, start_week=1, end_week=16, total_students=40, is_locked=True,
    )
    old_plan = SchedulePlan(semester_id=sem.id, org_node_id=dept.id, plan_name="旧草稿", version_tag="V0", run_mode="SINGLE_DEPT", is_published=False)
    db.add_all([task_free, task_locked, old_plan])
    db.flush()
    db.add(ScheduleDetail(plan_id=old_plan.id, task_id=task_locked.id, timeslot_id=ts1.id, classroom_id=r1.id, week_type=0))
    db.commit()

    # 联动重算验证：12学时、周1节(2学时/周)=6有效周；第3-4周设实训 -> 1-2,5-8周
    r_wp = client.put("/api/v1/week-plan/range", json={
        "semester_id": sem.id, "cohort_id": c1.id, "start_week": 3, "end_week": 4,
        "week_mode": "PRACTICUM", "block_course_name": "软件综合实训",
    })
    assert r_wp.status_code == 200
    db.refresh(task_free)
    assert mask_to_label(task_free.week_mask) == "1-2,5-8周"

    # 2. 局部一键重排：新方案必须同时包含新排的 task_free(ts2) 与原样继承的 task_locked(ts1)，不能丢课！
    r_solve = client.post("/api/v1/solver/one-click", json={"semester_id": sem.id, "org_node_id": dept.id})
    assert r_solve.status_code == 200
    new_pid = r_solve.json()["plan_id"]
    new_details = db.query(ScheduleDetail).filter(ScheduleDetail.plan_id == new_pid).all()
    assert len(new_details) == 2
    assert {d.task_id for d in new_details} == {task_free.id, task_locked.id}

    # 3. 正式发布前，学生调用 /my-schedule 看不到草稿课表；发布后立即可见！
    tok_stu = create_access_token(stu.id, stu.username, stu.role_code, dept.id)
    draft_sched = client.get("/api/v1/auth/my-schedule", headers={"Authorization": f"Bearer {tok_stu}"}).json()
    assert draft_sched["plan_id"] is None and len(draft_sched["cards"]) == 0

    assert client.post(f"/api/v1/workbench/plans/{new_pid}/publish").status_code == 200
    pub_sched = client.get("/api/v1/auth/my-schedule", headers={"Authorization": f"Bearer {tok_stu}"}).json()
    assert pub_sched["plan_id"] == new_pid and len(pub_sched["cards"]) == 2
