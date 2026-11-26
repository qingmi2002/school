"""V1.2 门禁测试：自定义系统名称、动态教师/学生/班级/固定与流动教室 CRUD、学期大周期与每天1-2节必排规则。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app


@pytest.fixture()
def api_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.post("/api/v1/auth/seed-demo")
    yield client
    app.dependency_overrides.clear()


def test_site_config_dynamic_resources_and_must_schedule_policy(api_client):
    # 1. 自定义系统名称与隐藏体验账号开关
    r_cfg = api_client.put(
        "/api/v1/resources/site-config",
        json={"site_name": "北方工大智能排课系统", "site_subtitle": "教务排课管理平台", "show_demo_accounts": False},
    )
    assert r_cfg.status_code == 200
    assert api_client.get("/api/v1/resources/site-config").json()["site_name"] == "北方工大智能排课系统"

    # 2. 创建新学期大周期
    r_sem = api_client.post(
        "/api/v1/resources/semesters",
        json={"code": "2026-2027-2", "name": "2026-2027学年第二学期", "total_weeks": 20, "start_date": "2027-03-01", "end_date": "2027-07-16", "is_current": True},
    )
    assert r_sem.status_code == 200
    sem_id = r_sem.json()["id"]

    # 3. 动态新增班级、固定教室、流动教室、教师、学生
    cohorts = api_client.get("/api/v1/resources/cohorts").json()
    org_id = cohorts[0]["org_node_id"]
    cohort_id = cohorts[0]["id"]

    r_room = api_client.post(
        "/api/v1/resources/classrooms",
        json={"room_code": "B-108", "building": "二教", "owner_org_id": org_id, "capacity": 50, "room_type": "NORMAL", "usage_mode": "FIXED", "fixed_cohort_id": cohort_id},
    )
    assert r_room.status_code == 200
    assert r_room.json()["usage_mode"] == "FIXED"

    # 切换为流动教室
    room_id = r_room.json()["id"]
    r_sw = api_client.patch(f"/api/v1/resources/classrooms/{room_id}/usage-mode?usage_mode=FLOATING")
    assert r_sw.status_code == 200
    assert r_sw.json()["usage_mode"] == "FLOATING"

    # 4. 自定义“每天第 1-2 节必须有课”大规则 + 单教师独立规则
    r_rule = api_client.post(
        "/api/v1/resources/policy-rules",
        json={"semester_id": sem_id, "target_type": "GLOBAL", "rule_type": "MUST_SCHEDULE", "day_of_week": 0, "period_index": 1, "remark": "每天1-2节必排"},
    )
    assert r_rule.status_code == 200
    rules = api_client.get(f"/api/v1/resources/policy-rules?semester_id={sem_id}").json()
    assert len(rules) == 1
    assert rules[0]["rule_type"] == "MUST_SCHEDULE"
