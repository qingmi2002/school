"""V1.4 门禁测试：周次位掩码位运算、班级整周实训设置、兄弟班级隔离及学生端自动跳过实训周显示。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.week_mask import (
    build_week_mask,
    mask_to_label,
    masks_overlap,
    subtract_blocked_weeks,
)
from app.db.session import Base, get_db
from app.main import app


def test_week_mask_bit_operations_and_labels():
    odd = build_week_mask(1, 18, 1)
    even = build_week_mask(1, 18, 2)
    assert masks_overlap(odd, even) is False
    assert mask_to_label(odd) == "1-17周(单)"
    assert mask_to_label(even) == "2-18周(双)"

    first_half = build_week_mask(1, 9, 0)
    second_half = build_week_mask(10, 18, 0)
    assert masks_overlap(first_half, second_half) is False

    full_16 = build_week_mask(1, 16, 0)
    practicum = build_week_mask(10, 11, 0)
    effective = subtract_blocked_weeks(full_16, practicum)
    assert mask_to_label(effective) == "1-9,12-16周"


@pytest.fixture()
def api_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)

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


def test_cohort_block_practicum_week_isolation_and_student_notice(api_client):
    cohorts = api_client.get("/api/v1/resources/cohorts").json()
    se_cohort = next(c for c in cohorts if c["cohort_code"] == "SE2401")
    ai_cohort = next(c for c in cohorts if c["cohort_code"] == "AI2401")

    # 设定软工2401班 第10-11周为整周实训
    r_put = api_client.put(
        "/api/v1/week-plan/range",
        json={
            "semester_id": 1,
            "cohort_id": se_cohort["id"],
            "start_week": 10,
            "end_week": 11,
            "week_mode": "PRACTICUM",
            "block_course_name": "Java企业级综合实训",
        },
    )
    assert r_put.status_code == 200

    # 验证班级周历矩阵：软工2401常规课有效周变为 1-9,12-18周，而智能2401不受影响仍为 1-18周
    matrix = api_client.get("/api/v1/week-plan/matrix?semester_id=1").json()
    se_row = next(r for r in matrix["rows"] if r["cohort_id"] == se_cohort["id"])
    ai_row = next(r for r in matrix["rows"] if r["cohort_id"] == ai_cohort["id"])
    assert se_row["effective_regular_label"] == "1-9,12-18周"
    assert ai_row["effective_regular_label"] == "1-18周"

    # 验证学生登录查看班级课表：顶部自带整周实训提醒，常规课周次标签自动剔除第10-11周
    login = api_client.post("/api/v1/auth/login", json={"username": "S202401", "password": "123456"}).json()
    sched = api_client.get("/api/v1/auth/my-schedule", headers={"Authorization": f"Bearer {login['access_token']}"}).json()
    assert len(sched["block_week_notices"]) == 2
    assert any("Java企业级综合实训" in n for n in sched["block_week_notices"])
    assert any(c["effective_weeks_label"] == "1-9,12-18周" for c in sched["cards"])
