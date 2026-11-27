"""核心数据表与外键/唯一约束测试（V1.4 共 20 张核心表，含班级周历 cohort_week_plan）。"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.db.org_presets import NODE_TYPE_DICTIONARY, ORG_ARCHETYPE_PRESETS, resolve_campus_boundary_id
from app.models import (
    NodeType,
    OrgNode,
    OrgResourceGrant,
    Semester,
    SysUser,
    Timeslot,
    Classroom,
    TeachingTask,
    SchedulePlan,
    ScheduleDetail,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    for item in NODE_TYPE_DICTIONARY:
        session.add(NodeType(**item))
    session.commit()
    yield session
    session.close()


def test_core_tables_registered():
    assert len(Base.metadata.tables) == 20


def test_multi_campus_boundary_resolution_and_lateral_grant(db_session):
    sem = Semester(code="2026-2027-1", name="2026秋", total_weeks=18, is_current=True)
    db_session.add(sem)
    db_session.flush()

    univ = OrgNode(node_code="U01", node_name="示范大学", node_type_code="SCHOOL", tree_path="/1/", depth=1, is_summary_node=True)
    db_session.add(univ)
    db_session.flush()

    campus_a = OrgNode(parent_id=univ.id, node_code="C01", node_name="主校区", node_type_code="CAMPUS", tree_path=f"/{univ.id}/2/", depth=2, is_campus_boundary=True)
    dept_cs = OrgNode(parent_id=None, node_code="D01", node_name="计算机系", node_type_code="DEPT", tree_path="/temp/", depth=3, is_scheduling_unit=True, has_room_pool=True)
    db_session.add(campus_a)
    db_session.flush()
    dept_cs.parent_id = campus_a.id
    dept_cs.tree_path = f"/{univ.id}/{campus_a.id}/3/"
    db_session.add(dept_cs)

    lab_center = OrgNode(parent_id=campus_a.id, node_code="L01", node_name="实训中心", node_type_code="TRAINING_CENTER", tree_path=f"/{univ.id}/{campus_a.id}/4/", depth=3, has_room_pool=True)
    db_session.add(lab_center)
    db_session.commit()

    node_map = {n.id: n for n in db_session.query(OrgNode).all()}
    assert resolve_campus_boundary_id(node_map, dept_cs.id) == campus_a.id

    grant = OrgResourceGrant(granter_org_id=lab_center.id, grantee_org_id=dept_cs.id, semester_id=sem.id, resource_type="ROOM_POOL", grant_mode="IDLE_ONLY")
    db_session.add(grant)
    db_session.commit()

    bad_grant = OrgResourceGrant(granter_org_id=dept_cs.id, grantee_org_id=dept_cs.id, semester_id=sem.id, resource_type="ROOM_POOL")
    db_session.add(bad_grant)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_room_slot_uniqueness_and_odd_even_week_reuse(db_session):
    sem = Semester(code="2026-2027-1", name="2026秋", total_weeks=18, is_current=True)
    dept = OrgNode(node_code="CS", node_name="计算机系", node_type_code="DEPT", tree_path="/1/", depth=1, is_scheduling_unit=True, has_room_pool=True, is_campus_boundary=True)
    db_session.add_all([sem, dept])
    db_session.flush()

    teacher = SysUser(username="T1001", real_name="张老师", org_node_id=dept.id, role_code="TEACHER", password_hash="hashed")
    slot = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一 1-2节")
    room = Classroom(room_code="LAB-402", building="信息楼", owner_org_id=dept.id, capacity=60, room_type="COMPUTER_LAB", env_tags=["Linux", "GPU"])
    db_session.add_all([teacher, slot, room])
    db_session.flush()

    task1 = TeachingTask(semester_id=sem.id, org_node_id=dept.id, course_code="CS101", course_name="数据结构", course_category="LAB", teacher_id=teacher.id, weekly_sessions=1, week_type=1, total_students=45)
    task2 = TeachingTask(semester_id=sem.id, org_node_id=dept.id, course_code="CS102", course_name="操作系统", course_category="LAB", teacher_id=teacher.id, weekly_sessions=1, week_type=2, total_students=45)
    plan = SchedulePlan(semester_id=sem.id, org_node_id=dept.id, plan_name="计算机系初稿", version_tag="V1", run_mode="SINGLE_DEPT")
    db_session.add_all([task1, task2, plan])
    db_session.flush()

    db_session.add(ScheduleDetail(plan_id=plan.id, task_id=task1.id, timeslot_id=slot.id, classroom_id=room.id, week_type=1))
    db_session.add(ScheduleDetail(plan_id=plan.id, task_id=task2.id, timeslot_id=slot.id, classroom_id=room.id, week_type=2))
    db_session.commit()

    db_session.add(ScheduleDetail(plan_id=plan.id, task_id=task2.id, timeslot_id=slot.id, classroom_id=room.id, week_type=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_presets_cover_single_dept_and_six_school_archetypes():
    assert "single_dept_standalone" in ORG_ARCHETYPE_PRESETS
    assert len(ORG_ARCHETYPE_PRESETS) == 7
