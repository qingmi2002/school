"""V1.1 门禁测试：多级排课管理员(校/院/系/专业)、教师个人课表、学生班级课表与 JWT 鉴权闭环。"""
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
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _login(client: TestClient, username: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    assert resp.status_code == 200
    return resp.json()


def test_six_roles_login_hierarchical_scope_and_personal_schedules(api_client):
    # 1. 校级管理员登录 -> 看到全校全部 8 个账号
    admin_data = _login(api_client, "admin")
    assert admin_data["user"]["role_code"] == "SUPER_ADMIN"
    r_all = api_client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {admin_data['access_token']}"})
    assert r_all.status_code == 200
    assert len(r_all.json()) == 8

    # 2. 专业级排课员登录 -> 仅看到本专业（软工专业）子树内账号，看不到人工智能专业和校级管理员
    major_data = _login(api_client, "major_admin")
    assert major_data["user"]["role_code"] == "MAJOR_SCHEDULER"
    r_major = api_client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {major_data['access_token']}"})
    major_usernames = {u["username"] for u in r_major.json()}
    assert "major_admin" in major_usernames
    assert "T1001" in major_usernames
    assert "S202401" in major_usernames
    assert "admin" not in major_usernames
    assert "T1002" not in major_usernames

    # 3. 教师 T1001 登录 -> 查看个人排课信息（仅含张明远教授的课程）
    t_data = _login(api_client, "T1001")
    r_t = api_client.get("/api/v1/auth/my-schedule", headers={"Authorization": f"Bearer {t_data['access_token']}"})
    assert r_t.status_code == 200
    t_body = r_t.json()
    assert t_body["owner_type"] == "TEACHER"
    assert len(t_body["cards"]) == 3  # 软件工程导论(2节) + Linux系统实训(单周1节)

    # 4. 学生 S202401 登录 -> 查看所属行政班（软工2401）课表（含校级公共课锁定）
    s_data = _login(api_client, "S202401")
    r_s = api_client.get("/api/v1/auth/my-schedule", headers={"Authorization": f"Bearer {s_data['access_token']}"})
    assert r_s.status_code == 200
    s_body = r_s.json()
    assert s_body["owner_type"] == "STUDENT"
    assert "软工2401" in s_body["sub_title"]
    assert any(c["is_public_lock"] for c in s_body["cards"])
    assert len(s_body["cards"]) == 6  # 4节专业课 + 2节校级公共课
