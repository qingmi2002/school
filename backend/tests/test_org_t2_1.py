"""T2.1 验收门禁测试：7 套组织架构一键无缝切换、横向借用授权校验、节点级作息覆写与 RBAC 子树隔离。"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.org_presets import ORG_ARCHETYPE_PRESETS
from app.db.session import Base
from app.models import OrgNode, SysUser
from app.org import (
    apply_org_preset,
    authorize_resource_access,
    build_org_tree,
    check_org_scope_permission,
    get_effective_timeslots,
    update_org_flags,
    upsert_node_timeslots,
    upsert_resource_grant,
)
from app.org.schemas import OrgFlagsUpdate, ResourceGrantUpsert, TimeslotItemIn


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_all_7_archetypes_switch_seamlessly(db_session):
    for preset_key in ORG_ARCHETYPE_PRESETS:
        nodes = apply_org_preset(db_session, preset_key=preset_key, clear_existing=True)
        assert len(nodes) >= 1
        tree = build_org_tree(db_session)
        assert len(tree) == 1
        # 多校区四级制验证校区边界向上溯源
        if preset_key == "multi_campus_four_tier":
            campus_main = db_session.query(OrgNode).filter(OrgNode.node_code == "MAIN_CAMPUS").first()
            cs_col = db_session.query(OrgNode).filter(OrgNode.node_code == "CS_COL").first()
            # 校验在树输出中 CS_COL 溯源到了 MAIN_CAMPUS
            main_dto = next(c for c in tree[0].children if c.id == campus_main.id)
            assert main_dto.children[0].id == cs_col.id
            assert main_dto.children[0].resolved_campus_id == campus_main.id


def test_lateral_resource_grant_and_ancestor_inheritance(db_session):
    apply_org_preset(db_session, "public_dept_and_training_center", clear_existing=True)
    univ = db_session.query(OrgNode).filter(OrgNode.node_code == "UNIV").first()
    pub_dept = db_session.query(OrgNode).filter(OrgNode.node_code == "BASIC_PUB").first()
    lab_center = db_session.query(OrgNode).filter(OrgNode.node_code == "LAB_CENTER").first()

    # 1. 未开通横向授权前，基础教学部无权借用实训中心机房
    denied = authorize_resource_access(db_session, pub_dept.id, lab_center.id, "ROOM_POOL")
    assert denied.allowed is False
    assert denied.access_via == "DENIED"

    # 2. 开通横向借用授权后放行
    upsert_resource_grant(
        db_session,
        ResourceGrantUpsert(
            granter_org_id=lab_center.id,
            grantee_org_id=pub_dept.id,
            resource_type="ROOM_POOL",
            grant_mode="IDLE_ONLY",
        ),
    )
    granted = authorize_resource_access(db_session, pub_dept.id, lab_center.id, "ROOM_POOL")
    assert granted.allowed is True
    assert granted.access_via == "LATERAL_GRANT"
    assert granted.grant_mode == "IDLE_ONLY"

    # 3. 动态开启校级节点 has_room_pool 开关后，下级自动向上继承
    update_org_flags(db_session, univ.id, OrgFlagsUpdate(has_room_pool=True))
    inherited = authorize_resource_access(db_session, pub_dept.id, univ.id, "ROOM_POOL")
    assert inherited.allowed is True
    assert inherited.access_via == "ANCESTOR_INHERIT"


def test_node_level_timeslot_override_and_inheritance(db_session):
    apply_org_preset(db_session, "multi_campus_four_tier", clear_existing=True)
    main_campus = db_session.query(OrgNode).filter(OrgNode.node_code == "MAIN_CAMPUS").first()
    new_campus = db_session.query(OrgNode).filter(OrgNode.node_code == "NEW_CAMPUS").first()
    cs_col = db_session.query(OrgNode).filter(OrgNode.node_code == "CS_COL").first()

    # 设置全校默认作息（08:00 上课）
    upsert_node_timeslots(
        db_session,
        org_node_id=None,
        items=[TimeslotItemIn(day_of_week=1, period_index=1, period_name="1-2节", start_time="08:00", end_time="09:40")],
    )
    # 新校区自由覆写作息（08:30 上课）
    upsert_node_timeslots(
        db_session,
        org_node_id=new_campus.id,
        items=[TimeslotItemIn(day_of_week=1, period_index=1, period_name="新校区1-2节", start_time="08:30", end_time="10:10")],
    )

    eff_new = get_effective_timeslots(db_session, new_campus.id)
    assert eff_new.inherited is False
    assert eff_new.timeslots[0].start_time == "08:30"

    eff_cs = get_effective_timeslots(db_session, cs_col.id)
    assert eff_cs.inherited is True
    assert eff_cs.source_org_node_id is None
    assert eff_cs.timeslots[0].start_time == "08:00"


def test_rbac_subtree_isolation(db_session):
    apply_org_preset(db_session, "school_college_dept", clear_existing=True)
    univ = db_session.query(OrgNode).filter(OrgNode.node_code == "UNIV").first()
    col = db_session.query(OrgNode).filter(OrgNode.node_code == "INFO_COL").first()
    dept = db_session.query(OrgNode).filter(OrgNode.node_code == "CS_DEPT").first()

    col_scheduler = SysUser(username="S01", real_name="院排课员", org_node_id=col.id, role_code="DEPT_SCHEDULER", password_hash="x")
    admin = SysUser(username="A01", real_name="校管理员", org_node_id=univ.id, role_code="SUPER_ADMIN", password_hash="x")

    # 院排课员可管下属系部，但无权越级修改校级节点
    ok_child, _ = check_org_scope_permission(col_scheduler, col, dept, "SCHEDULE")
    ok_parent, _ = check_org_scope_permission(col_scheduler, col, univ, "SCHEDULE")
    ok_admin, _ = check_org_scope_permission(admin, univ, dept, "SCHEDULE")
    assert ok_child is True
    assert ok_parent is False
    assert ok_admin is True
