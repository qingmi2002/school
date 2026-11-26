"""V1.3 门禁测试：组织机构自定义 CRUD、独立教学楼数据表及 6-Sheet 基础数据集中幂等导入。"""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.importer.master_data_importer import build_master_data_template
from app.main import app


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
    yield client
    app.dependency_overrides.clear()


def test_master_6_sheet_import_and_custom_org_building_crud(api_client):
    # 1. 下载 6 合 1 集中导入模板并直接上传全量入库
    r_tpl = api_client.get("/api/v1/resources/master-import/template")
    assert r_tpl.status_code == 200
    tpl_bytes = build_master_data_template()

    r_up = api_client.post(
        "/api/v1/resources/master-import/upload",
        files={"file": ("master.xlsx", tpl_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r_up.status_code == 200
    body = r_up.json()
    assert body["status"] == "SUCCESS"
    assert body["total_errors"] == 0
    assert body["total_inserted"] == 11  # 4组织 + 2教学楼 + 2教室 + 1班级 + 1教师 + 1学生

    # 2. 幂等二次上传验证全部走 updated，不重复插入
    r_up2 = api_client.post(
        "/api/v1/resources/master-import/upload",
        files={"file": ("master.xlsx", tpl_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r_up2.json()["total_inserted"] == 0
    assert r_up2.json()["total_updated"] == 11

    # 3. 验证教学楼表已入库且可新增
    bldgs = api_client.get("/api/v1/resources/buildings").json()
    assert len(bldgs) == 2

    # 4. 自定义新增、重命名与删除组织机构节点
    tree = api_client.get("/api/v1/org/tree").json()
    root_id = tree[0]["id"]
    r_new = api_client.post(
        "/api/v1/org/nodes",
        json={"parent_id": root_id, "node_code": "COL_NEW", "node_name": "理学院", "node_type_code": "COLLEGE"},
    )
    assert r_new.status_code == 200
    nid = r_new.json()["id"]
    assert api_client.patch(f"/api/v1/org/nodes/{nid}", json={"node_name": "数理学院"}).status_code == 200
    assert api_client.delete(f"/api/v1/org/nodes/{nid}").status_code == 200
