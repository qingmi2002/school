"""V1.5 验收测试：课程库/班级选课/指定合班耦合、固定教室独占 vs 流动教室合班、教师分级权限与一键智能排课。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Classroom, OrgNode, Semester, StudentCohort, SysUser, Timeslot
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


def test_v1_5_course_merge_fixed_room_exclusive_and_one_click_solve(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    sem = Semester(code="2026-2027-2", name="2026春", total_weeks=18, is_current=True)
    db.add(sem)
    db.flush()

    for d in range(1, 6):
        for p in range(1, 4):
            db.add(Timeslot(org_node_id=None, day_of_week=d, period_index=p, period_name=f"周{d}-{p}"))

    c1 = StudentCohort(org_node_id=dept.id, cohort_code="SE2401", cohort_name="软件2401", student_count=45, grade_year=2024)
    c2 = StudentCohort(org_node_id=dept.id, cohort_code="SE2402", cohort_name="软件2402", student_count=45, grade_year=2024)
    c3 = StudentCohort(org_node_id=dept.id, cohort_code="SE2403", cohort_name="软件2403", student_count=42, grade_year=2024)
    db.add_all([c1, c2, c3])
    db.flush()

    # 教室：c1 专属固定教室(50座)、大容量流动阶梯教室(120座)、流动机房(60座)
    r_fixed = Classroom(
        room_code="A-101", building="主楼", owner_org_id=dept.id, capacity=50,
        room_type="NORMAL", usage_mode="FIXED", fixed_cohort_id=c1.id,
    )
    r_hall = Classroom(
        room_code="B-301", building="主楼", owner_org_id=dept.id, capacity=120,
        room_type="LECTURE_HALL", usage_mode="FLOATING",
    )
    r_lab = Classroom(
        room_code="LAB-401", building="实验楼", owner_org_id=dept.id, capacity=60,
        room_type="COMPUTER_LAB", usage_mode="FLOATING",
    )
    t_zhang = SysUser(
        username="t_zhang", real_name="张老师", org_node_id=dept.id,
        role_code="TEACHER", teacher_priority=3, password_hash=hash_password("123456"),
    )
    t_lead = SysUser(
        username="lead_se", real_name="王主任", org_node_id=dept.id,
        role_code="TEACHING_LEAD", teacher_priority=2, password_hash=hash_password("123456"),
    )
    admin = SysUser(
        username="admin", real_name="管理员", org_node_id=dept.id,
        role_code="SUPER_ADMIN", password_hash=hash_password("123456"),
    )
    db.add_all([r_fixed, r_hall, r_lab, t_zhang, t_lead, admin])
    db.commit()

    # 1. 建课程库：高等数学(可合班阶梯教室)、Python上机(机房)、软件导论(普通教室)
    rc1 = client.post("/api/v1/curriculum/courses", json={
        "owner_org_id": dept.id, "course_code": "MATH101", "course_name": "高等数学",
        "course_category": "THEORY", "required_room_type": "LECTURE_HALL", "default_weekly_sessions": 2, "allow_combined": True,
    })
    assert rc1.status_code == 200
    rc2 = client.post("/api/v1/curriculum/courses", json={
        "owner_org_id": dept.id, "course_code": "PY201", "course_name": "Python上机",
        "course_category": "LAB", "required_room_type": "COMPUTER_LAB", "default_weekly_sessions": 1, "allow_combined": False,
    })
    assert rc2.status_code == 200
    rc3 = client.post("/api/v1/curriculum/courses", json={
        "owner_org_id": dept.id, "course_code": "SE100", "course_name": "软件导论",
        "course_category": "THEORY", "required_room_type": "NORMAL", "default_weekly_sessions": 1, "allow_combined": True,
    })
    assert rc3.status_code == 200

    # 2. 班级选课 + 指定 c1 & c2 合班上高等数学（自动累计 90 人），张老师同时带多门课多个班
    rt_a = client.post("/api/v1/curriculum/tasks", json={
        "semester_id": sem.id, "course_id": rc1.json()["id"], "teacher_id": t_zhang.id, "cohort_ids": [c1.id],
    })
    rt_b = client.post("/api/v1/curriculum/tasks", json={
        "semester_id": sem.id, "course_id": rc1.json()["id"], "teacher_id": t_zhang.id, "cohort_ids": [c2.id],
    })
    assert rt_a.status_code == 200 and rt_b.status_code == 200
    merged = client.post("/api/v1/curriculum/tasks/merge", json={"task_ids": [rt_a.json()["id"], rt_b.json()["id"]]})
    assert merged.status_code == 200
    assert merged.json()["is_combined"] is True
    assert merged.json()["total_students"] == 90

    # c1 单班上软件导论（应落入自己的固定教室 A-101）+ c1 上 Python上机（应落入机房 LAB-401）
    rt_c1_theory = client.post("/api/v1/curriculum/tasks", json={
        "semester_id": sem.id, "course_id": rc3.json()["id"], "teacher_id": t_zhang.id, "cohort_ids": [c1.id],
    })
    rt_c1_lab = client.post("/api/v1/curriculum/tasks", json={
        "semester_id": sem.id, "course_id": rc2.json()["id"], "teacher_id": t_lead.id, "cohort_ids": [c1.id],
    })
    assert rt_c1_theory.status_code == 200 and rt_c1_lab.status_code == 200

    # 3. 教师多课多班负荷汇总
    wl = client.get("/api/v1/curriculum/teacher-workload", params={"semester_id": sem.id}).json()
    zhang_wl = next(x for x in wl if x["teacher_id"] == t_zhang.id)
    assert zhang_wl["task_count"] == 2
    assert zhang_wl["combined_task_count"] == 1
    assert zhang_wl["total_weekly_sessions"] == 3

    # 4. 教师自主禁排权限隔离与窗口开关
    tok_zhang = create_access_token(t_zhang.id, t_zhang.username, t_zhang.role_code, dept.id)
    tok_lead = create_access_token(t_lead.id, t_lead.username, t_lead.role_code, dept.id)
    tok_admin = create_access_token(admin.id, admin.username, admin.role_code, dept.id)
    first_ts = db.query(Timeslot).order_by(Timeslot.id).first()

    # 普通教师可填本人
    r_self = client.put(
        "/api/v1/constraints/teacher-unavailable",
        headers={"Authorization": f"Bearer {tok_zhang}"},
        json={"semester_id": sem.id, "teacher_id": t_zhang.id, "slots": [{"timeslot_id": first_ts.id, "constraint_level": "HARD", "reason": "科研例会"}]},
    )
    assert r_self.status_code == 200
    # 普通教师不可越权改他人
    r_other = client.put(
        "/api/v1/constraints/teacher-unavailable",
        headers={"Authorization": f"Bearer {tok_zhang}"},
        json={"semester_id": sem.id, "teacher_id": t_lead.id, "slots": []},
    )
    assert r_other.status_code == 403
    # 教研室主任可管理本系教师
    r_lead_ok = client.get(
        "/api/v1/constraints/teacher-unavailable",
        headers={"Authorization": f"Bearer {tok_lead}"},
        params={"semester_id": sem.id, "teacher_id": t_zhang.id},
    )
    assert r_lead_ok.status_code == 200 and len(r_lead_ok.json()) == 1
    # 管理员关闭填报窗口后，普通教师写入被拦截
    assert client.put("/api/v1/constraints/teacher-unavail-window", headers={"Authorization": f"Bearer {tok_admin}"}, json={"is_open": False}).status_code == 200
    r_closed = client.put(
        "/api/v1/constraints/teacher-unavailable",
        headers={"Authorization": f"Bearer {tok_zhang}"},
        json={"semester_id": sem.id, "teacher_id": t_zhang.id, "slots": []},
    )
    assert r_closed.status_code == 403

    # 5. 一键智能排课直接落库，并验证：合班走 B-301、c1 普通课走固定教室 A-101、上机课走 LAB-401、张老师避开禁排槽
    solve_res = client.post("/api/v1/solver/one-click", json={"semester_id": sem.id, "org_node_id": dept.id})
    assert solve_res.status_code == 200
    body = solve_res.json()
    assert body["scheduled_count"] == 4
    assert body["unscheduled_count"] == 0

    wb = client.get(f"/api/v1/workbench/plans/{body['plan_id']}").json()
    cards = wb["cards"]
    math_cards = [c for c in cards if c["course_code"] == "MATH101"]
    se_cards = [c for c in cards if c["course_code"] == "SE100"]
    py_cards = [c for c in cards if c["course_code"] == "PY201"]
    assert all(c["room_code"] == "B-301" for c in math_cards)
    assert all(c["room_code"] == "A-101" for c in se_cards)
    assert all(c["room_code"] == "LAB-401" for c in py_cards)
    assert all(c["timeslot_id"] != first_ts.id for c in cards if c["teacher_id"] == t_zhang.id)
