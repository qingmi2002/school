"""V1.8 验收测试：全读/写鉴权、跨院系 IDOR 越权拦截、登录防爆破、文件魔数校验 + 智能对调、空教室查询、学期结转、总课表看板。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import reset_login_rate_limit
from app.auth.security import create_access_token, hash_password
from app.core.config import settings
from app.core.week_mask import build_week_mask
from app.db.session import Base, get_db
from app.main import app
from app.org import apply_org_preset
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


@pytest.fixture()
def client_and_db():
    reset_login_rate_limit()
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
    reset_login_rate_limit()
    db.close()


def test_v1_8_security_get_auth_idor_bruteforce_and_upload_validation(client_and_db):
    client, db = client_and_db
    # 建两个独立院系测试跨院系 IDOR 越权拦截
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept_a = db.query(OrgNode).first()
    dept_b = OrgNode(
        parent_id=dept_a.parent_id,
        node_code="FL",
        node_name="外语系",
        node_type_code=dept_a.node_type_code,
        tree_path="/99/",
        depth=dept_a.depth,
    )
    db.add(dept_b)
    db.flush()

    admin_a = SysUser(username="admin_a", real_name="A系管理员", org_node_id=dept_a.id, role_code="DEPT_SCHEDULER", password_hash=hash_password("123456"))
    student_a = SysUser(username="stu_a", real_name="学生甲", org_node_id=dept_a.id, role_code="STUDENT", password_hash=hash_password("123456"))
    db.add_all([admin_a, student_a])
    db.commit()

    tok_a = create_access_token(admin_a.id, admin_a.username, admin_a.role_code, dept_a.id)
    tok_stu = create_access_token(student_a.id, student_a.username, student_a.role_code, dept_a.id)

    settings.ENFORCE_API_AUTH = True
    try:
        # 1. 未登录 GET 敏感接口必须 401；公开 site-config 放行 200
        assert client.get("/api/v1/resources/students").status_code == 401
        assert client.get("/api/v1/resources/site-config").status_code == 200
        # 学生尝试拉取全校学生名单必须 403
        assert client.get("/api/v1/resources/students", headers={"Authorization": f"Bearer {tok_stu}"}).status_code == 403
        # 管理员拉取 200
        assert client.get("/api/v1/resources/students", headers={"Authorization": f"Bearer {tok_a}"}).status_code == 200

        # 2. 跨院系 IDOR 越权拦截：A系管理员尝试给 B系建课必须 403
        r_idor = client.post(
            "/api/v1/curriculum/courses",
            headers={"Authorization": f"Bearer {tok_a}"},
            json={"owner_org_id": dept_b.id, "course_code": "FL101", "course_name": "法语"},
        )
        assert r_idor.status_code == 403

        # 3. 恶意伪造 .xlsx 文件上传拦截（魔数不对）
        r_bad_file = client.post(
            "/api/v1/import/validate?mode=A",
            headers={"Authorization": f"Bearer {tok_a}"},
            files={"file": ("evil.xlsx", b"NOT_A_REAL_ZIP_CONTENT", "application/octet-stream")},
        )
        assert r_bad_file.status_code == 400

        # 4. 登录防爆破限流：连续输错 5 次触发 429
        for _ in range(5):
            assert client.post("/api/v1/auth/login", json={"username": "admin_a", "password": "wrong"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"username": "admin_a", "password": "123456"}).status_code == 429
    finally:
        settings.ENFORCE_API_AUTH = False


def test_v1_8_smart_swap_free_rooms_semester_clone_and_analytics(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    sem1 = Semester(code="2026-1", name="2026秋", total_weeks=18, is_current=True)
    sem2 = Semester(code="2026-2", name="2027春", total_weeks=18, is_current=False)
    db.add_all([sem1, sem2])
    db.flush()

    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一1-2")
    ts2 = Timeslot(org_node_id=None, day_of_week=2, period_index=1, period_name="周二1-2")
    c1 = StudentCohort(org_node_id=dept.id, cohort_code="SE2401", cohort_name="软件2401", student_count=45, grade_year=2024)
    r1 = Classroom(room_code="A-101", building="主楼", owner_org_id=dept.id, capacity=60, room_type="NORMAL", usage_mode="FLOATING")
    r2 = Classroom(room_code="A-102", building="主楼", owner_org_id=dept.id, capacity=60, room_type="NORMAL", usage_mode="FLOATING")
    t1 = SysUser(username="t1", real_name="张老师", org_node_id=dept.id, role_code="TEACHER", password_hash="x")
    t2 = SysUser(username="t2", real_name="李老师", org_node_id=dept.id, role_code="TEACHER", password_hash="x")
    db.add_all([ts1, ts2, c1, r1, r2, t1, t2])
    db.flush()

    task_a = TeachingTask(
        semester_id=sem1.id, org_node_id=dept.id, course_code="C1", course_name="数据结构",
        course_category="THEORY", teacher_id=t1.id, cohort_ids=[c1.id], weekly_sessions=1,
        week_type=0, start_week=1, end_week=16, week_mask=build_week_mask(1, 16, 0), total_students=45,
    )
    task_b = TeachingTask(
        semester_id=sem1.id, org_node_id=dept.id, course_code="C2", course_name="操作系统",
        course_category="THEORY", teacher_id=t2.id, cohort_ids=[c1.id], weekly_sessions=1,
        week_type=0, start_week=1, end_week=16, week_mask=build_week_mask(1, 16, 0), total_students=45,
    )
    plan = SchedulePlan(semester_id=sem1.id, org_node_id=dept.id, plan_name="V1.8方案", version_tag="V1", run_mode="SINGLE_DEPT", is_published=True)
    db.add_all([task_a, task_b, plan])
    db.flush()

    det_a = ScheduleDetail(plan_id=plan.id, task_id=task_a.id, timeslot_id=ts1.id, classroom_id=r1.id, week_type=0, week_mask=task_a.week_mask)
    det_b = ScheduleDetail(plan_id=plan.id, task_id=task_b.id, timeslot_id=ts2.id, classroom_id=r2.id, week_type=0, week_mask=task_b.week_mask)
    db.add_all([det_a, det_b])
    db.commit()

    # 1. 智能对调（Swap）：A 与 B 互换时间片与教室
    sw = client.post("/api/v1/validator/swap", json={"plan_id": plan.id, "detail_id_a": det_a.id, "detail_id_b": det_b.id})
    assert sw.status_code == 200 and sw.json()["swapped"] is True
    det_a_new = db.get(ScheduleDetail, det_a.id)
    det_b_new = db.get(ScheduleDetail, det_b.id)
    assert det_a_new.timeslot_id == ts2.id and det_b_new.timeslot_id == ts1.id

    # 2. 空教室实时查询：第 1 周周一 1-2 节 r2 被 B 占用，仅剩 r1 空闲；第 18 周两间都空闲
    fr1 = client.get("/api/v1/workbench/free-rooms", params={"semester_id": sem1.id, "week_no": 1, "day_of_week": 1, "period_index": 1}).json()
    assert fr1["free_count"] == 1 and fr1["free_rooms"][0]["room_code"] == "A-102"
    fr18 = client.get("/api/v1/workbench/free-rooms", params={"semester_id": sem1.id, "week_no": 18, "day_of_week": 1, "period_index": 1}).json()
    assert fr18["free_count"] == 2

    # 3. 历史学期一键结转复用（含幂等去重）
    cl1 = client.post("/api/v1/curriculum/tasks/clone-semester", json={"source_semester_id": sem1.id, "target_semester_id": sem2.id}).json()
    assert cl1["cloned_count"] == 2 and cl1["skipped_count"] == 0
    cl2 = client.post("/api/v1/curriculum/tasks/clone-semester", json={"source_semester_id": sem1.id, "target_semester_id": sem2.id}).json()
    assert cl2["cloned_count"] == 0 and cl2["skipped_count"] == 2

    # 4. 全院总课表与利用率看板
    an = client.get(f"/api/v1/workbench/plans/{plan.id}/analytics").json()
    assert an["completion_rate"] == 100.0
    assert len(an["master_matrix"]) == 1
    assert len(an["room_utilization"]) == 2
