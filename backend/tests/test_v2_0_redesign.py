"""V2.0 验收测试：班级入学至毕业全周期、多级组织节点职能管理员、师生专属个人概览、各业务域独立导出 Excel。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Classroom, OrgNode, Semester, StudentCohort, SysUser, TeachingTask
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


def test_v2_0_cohort_lifecycle_org_managers_personal_overview_and_exports(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    sem = Semester(code="2026-1", name="2026秋", total_weeks=18, is_current=True)
    db.add(sem)
    db.flush()

    teacher = SysUser(username="t_wang", real_name="王老师", org_node_id=dept.id, role_code="TEACHER", teacher_priority=2, password_hash=hash_password("123456"))
    db.add(teacher)
    db.commit()

    # 1. 班级全生命周期（入学 2024 + 4 年制 -> 自动计算 2028 毕业 + 归档切换）
    rc = client.post("/api/v1/resources/cohorts", json={
        "cohort_code": "SE2401", "cohort_name": "软件工程2401", "org_node_id": dept.id,
        "grade_year": 2024, "study_years": 4, "student_count": 44,
    })
    assert rc.status_code == 200
    cdata = rc.json()
    assert cdata["graduation_year"] == 2028 and cdata["cohort_status"] == "ACTIVE"
    assert client.patch(f"/api/v1/resources/cohorts/{cdata['id']}/status", params={"cohort_status": "GRADUATED"}).status_code == 200
    assert len(client.get("/api/v1/resources/cohorts", params={"cohort_status": "GRADUATED"}).json()) == 1
    assert client.patch(f"/api/v1/resources/cohorts/{cdata['id']}/status", params={"cohort_status": "ACTIVE"}).status_code == 200

    # 2. 多级组织节点自定义职能管理员绑定，并在 /auth/me 返回 managed_nodes
    rm = client.post(f"/api/v1/org/nodes/{dept.id}/managers", json={
        "user_id": teacher.id, "title_name": "软件工程专业负责人", "permission_level": "SCHEDULER",
    })
    assert rm.status_code == 200
    assert len(client.get(f"/api/v1/org/nodes/{dept.id}/managers").json()) == 1

    tok_t = create_access_token(teacher.id, teacher.username, teacher.role_code, dept.id)
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok_t}"}).json()
    assert len(me["managed_nodes"]) == 1 and me["managed_nodes"][0]["title_name"] == "软件工程专业负责人"

    # 3. 师生专属个人工作台概览 (/auth/my-overview)
    stu = SysUser(username="s2401", real_name="李同学", org_node_id=dept.id, cohort_id=cdata["id"], role_code="STUDENT", password_hash=hash_password("123456"))
    room = Classroom(room_code="A-201", building="主楼", owner_org_id=dept.id, capacity=50, room_type="NORMAL", usage_mode="FIXED", fixed_cohort_id=cdata["id"])
    task = TeachingTask(semester_id=sem.id, org_node_id=dept.id, course_code="CS101", course_name="程序设计", course_category="THEORY", teacher_id=teacher.id, cohort_ids=[cdata["id"]], weekly_sessions=2, total_hours=32, total_students=44)
    db.add_all([stu, room, task])
    db.commit()

    ov_t = client.get("/api/v1/auth/my-overview", headers={"Authorization": f"Bearer {tok_t}"}).json()
    assert ov_t["view_type"] == "TEACHER" and ov_t["total_semester_hours"] == 32

    tok_s = create_access_token(stu.id, stu.username, stu.role_code, dept.id)
    ov_s = client.get("/api/v1/auth/my-overview", headers={"Authorization": f"Bearer {tok_s}"}).json()
    assert ov_s["view_type"] == "STUDENT" and ov_s["cohort_lifecycle"]["graduation_year"] == 2028
    assert ov_s["cohort_lifecycle"]["fixed_room_code"] == "A-201"
    assert len(ov_s["my_courses"]) == 1

    # 4. 各业务模块专属 Excel 导出
    for dom in ("teachers", "students", "cohorts", "classrooms"):
        rx = client.get(f"/api/v1/resources/export/{dom}")
        assert rx.status_code == 200 and rx.content[:4] == b"PK\x03\x04"
