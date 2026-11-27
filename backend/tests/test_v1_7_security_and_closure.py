"""V1.7 安全加固与闭环验收测试：服务端写接口 RBAC 拦截、修改/重置密码、演示初始化保护、拖拽 week_mask 对齐及方案发布/锁定。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token, hash_password
from app.core.config import settings
from app.core.week_mask import build_week_mask
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    Classroom,
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
from app.validator import check_drag_target
from app.validator.schemas import DragCheckRequest


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


def test_v1_7_strict_write_auth_rbac_and_password_management(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    admin = SysUser(username="admin", real_name="管理员", org_node_id=dept.id, role_code="SUPER_ADMIN", password_hash=hash_password("123456"))
    teacher = SysUser(username="t_li", real_name="李老师", org_node_id=dept.id, role_code="TEACHER", password_hash=hash_password("123456"))
    db.add_all([admin, teacher])
    db.commit()

    tok_admin = create_access_token(admin.id, admin.username, admin.role_code, dept.id)
    tok_teacher = create_access_token(teacher.id, teacher.username, teacher.role_code, dept.id)

    # 开启生产级严格鉴权
    settings.ENFORCE_API_AUTH = True
    try:
        # 1. 未登录调用写接口直接 401
        r_unauth = client.post("/api/v1/curriculum/courses", json={"course_code": "X1", "course_name": "测试课"})
        assert r_unauth.status_code == 401

        # 2. 普通教师调用管理员写接口直接 403
        r_forbid = client.post(
            "/api/v1/curriculum/courses",
            headers={"Authorization": f"Bearer {tok_teacher}"},
            json={"course_code": "X1", "course_name": "测试课"},
        )
        assert r_forbid.status_code == 403

        # 3. 管理员正常写入 200
        r_ok = client.post(
            "/api/v1/curriculum/courses",
            headers={"Authorization": f"Bearer {tok_admin}"},
            json={"course_code": "X1", "course_name": "测试课"},
        )
        assert r_ok.status_code == 200

        # 4. 教师自助改密成功，且旧密码失效、新密码可登录
        r_chg = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {tok_teacher}"},
            json={"old_password": "123456", "new_password": "NewPassword_2026"},
        )
        assert r_chg.status_code == 200
        assert client.post("/api/v1/auth/login", json={"username": "t_li", "password": "123456"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"username": "t_li", "password": "NewPassword_2026"}).status_code == 200

        # 5. 管理员重置教师密码
        r_rst = client.post(
            "/api/v1/auth/reset-password",
            headers={"Authorization": f"Bearer {tok_admin}"},
            json={"user_id": teacher.id, "new_password": "Reset_2026"},
        )
        assert r_rst.status_code == 200
        assert client.post("/api/v1/auth/login", json={"username": "t_li", "password": "Reset_2026"}).status_code == 200
    finally:
        settings.ENFORCE_API_AUTH = False


def test_v1_7_drag_validator_week_mask_alignment_and_plan_publish_lock(client_and_db):
    client, db = client_and_db
    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    sem = Semester(code="2026-2027-2", name="2026春", total_weeks=18, is_current=True)
    db.add(sem)
    db.flush()

    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一1-2")
    ts2 = Timeslot(org_node_id=None, day_of_week=1, period_index=2, period_name="周一3-4")
    c1 = StudentCohort(org_node_id=dept.id, cohort_code="SE2401", cohort_name="软件2401", student_count=40, grade_year=2024)
    r1 = Classroom(room_code="R-101", building="主楼", owner_org_id=dept.id, capacity=60, room_type="NORMAL", usage_mode="FLOATING")
    t1 = SysUser(username="t1", real_name="张老师", org_node_id=dept.id, role_code="TEACHER", password_hash="x")
    db.add_all([ts1, ts2, c1, r1, t1])
    db.flush()

    # 任务1(1-8周) 与 任务2(9-16周) 同师同班同教室，拖到同一时间片应判定为 GREEN（不误报红灯）
    task1 = TeachingTask(
        semester_id=sem.id, org_node_id=dept.id, course_code="P1", course_name="前半学期课",
        course_category="THEORY", teacher_id=t1.id, cohort_ids=[c1.id], weekly_sessions=1,
        week_type=0, start_week=1, end_week=8, week_mask=build_week_mask(1, 8, 0), total_students=40,
    )
    task2 = TeachingTask(
        semester_id=sem.id, org_node_id=dept.id, course_code="P2", course_name="后半学期课",
        course_category="THEORY", teacher_id=t1.id, cohort_ids=[c1.id], weekly_sessions=1,
        week_type=0, start_week=9, end_week=16, week_mask=build_week_mask(9, 16, 0), total_students=40,
    )
    plan = SchedulePlan(semester_id=sem.id, org_node_id=dept.id, plan_name="V1.7方案", version_tag="V1", run_mode="SINGLE_DEPT")
    db.add_all([task1, task2, plan])
    db.flush()

    d1 = ScheduleDetail(plan_id=plan.id, task_id=task1.id, timeslot_id=ts1.id, classroom_id=r1.id, week_type=0, week_mask=task1.week_mask)
    d2 = ScheduleDetail(plan_id=plan.id, task_id=task2.id, timeslot_id=ts2.id, classroom_id=r1.id, week_type=0, week_mask=task2.week_mask)
    db.add_all([d1, d2])
    # 周期规则禁排周一3-4节
    db.add(SchedulePolicyRule(semester_id=sem.id, target_type="GLOBAL", rule_type="FORBID_SCHEDULE", day_of_week=1, period_index=2, remark="全校例会"))
    db.commit()

    # 将 9-16周 的 d2 拖到 1-8周 的 ts1 -> 应为 GREEN（分段周复用合法）
    res_green = check_drag_target(db, DragCheckRequest(plan_id=plan.id, detail_id=d2.id, target_timeslot_id=ts1.id, target_classroom_id=r1.id, scope="SINGLE_DEPT"))
    assert res_green.light == "GREEN"

    # 将 d1 拖到被周期禁排的 ts2 -> 应为 RED
    res_red = check_drag_target(db, DragCheckRequest(plan_id=plan.id, detail_id=d1.id, target_timeslot_id=ts2.id, target_classroom_id=r1.id, scope="SINGLE_DEPT"))
    assert res_red.light == "RED"

    # 方案列表、发布与单课锁定接口验证
    assert len(client.get("/api/v1/workbench/plans").json()) == 1
    assert client.post(f"/api/v1/workbench/plans/{plan.id}/publish").status_code == 200
    assert client.get("/api/v1/workbench/plans").json()[0]["is_published"] is True
    assert client.patch(f"/api/v1/workbench/tasks/{task1.id}/lock", json={"is_locked": True}).json()["is_locked"] is True
