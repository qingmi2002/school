"""T2.2 验收门禁测试：分级锁定继承与兄弟隔离、下级越权防删、求解器严格避让已锁时间片及一键发布方案为基线。"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.locks import (
    delete_baseline_lock,
    get_effective_locks_for_node,
    publish_plan_as_baseline,
    upsert_baseline_locks,
)
from app.locks.schemas import BaselineLockBatchCreate, PublicLockItemIn
from app.models import (
    Classroom,
    OrgNode,
    Semester,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org import apply_org_preset, create_org_node
from app.org.schemas import OrgNodeCreate
from app.solver import CourseScheduleSolver
from app.solver.db_loader import load_solver_input_from_db, persist_solver_result


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


def test_hierarchical_lock_inheritance_isolation_and_solver_avoidance(db_session):
    apply_org_preset(db_session, "school_college_dept", clear_existing=True)
    univ = db_session.query(OrgNode).filter(OrgNode.node_code == "UNIV").first()
    info_col = db_session.query(OrgNode).filter(OrgNode.node_code == "INFO_COL").first()
    cs_dept = db_session.query(OrgNode).filter(OrgNode.node_code == "CS_DEPT").first()

    # 新增兄弟学院（机电学院），验证信息学院局部锁定不误伤兄弟学院
    mech_col = create_org_node(
        db_session,
        OrgNodeCreate(
            parent_id=univ.id,
            node_code="MECH_COL",
            node_name="机电学院",
            node_type_code="COLLEGE",
            is_scheduling_unit=True,
        ),
    )

    sem = Semester(code="2026-2027-1", name="2026秋", total_weeks=18, is_current=True)
    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一 1-2节")
    ts2 = Timeslot(org_node_id=None, day_of_week=1, period_index=2, period_name="周一 3-4节")
    db_session.add_all([sem, ts1, ts2])
    db_session.flush()

    cohort_cs = StudentCohort(cohort_code="CS2401", cohort_name="计科2401", org_node_id=cs_dept.id, grade_year=2024, student_count=40)
    teacher = SysUser(username="T2001", real_name="李老师", org_node_id=cs_dept.id, role_code="TEACHER", password_hash="x")
    room = Classroom(room_code="CS-101", building="信息楼", owner_org_id=cs_dept.id, capacity=60, room_type="NORMAL")
    db_session.add_all([cohort_cs, teacher, room])
    db_session.flush()

    # 1. 校级下发公共课锁定（锁定周一 1-2 节）
    univ_locks = upsert_baseline_locks(
        db_session,
        BaselineLockBatchCreate(
            semester_id=sem.id,
            lock_scope_org_id=univ.id,
            items=[PublicLockItemIn(timeslot_id=ts1.id, cohort_id=cohort_cs.id, course_name="大学英语(校级公共)")],
        ),
    )
    # 2. 信息学院下发院级基础课锁定
    upsert_baseline_locks(
        db_session,
        BaselineLockBatchCreate(
            semester_id=sem.id,
            lock_scope_org_id=info_col.id,
            items=[PublicLockItemIn(timeslot_id=ts1.id, classroom_id=room.id, course_name="工程导论(院级基础)")],
        ),
    )

    # 校验：计算机系继承校级 + 信息学院共 2 条锁定；机电学院仅继承校级 1 条锁定
    eff_cs = get_effective_locks_for_node(db_session, sem.id, cs_dept.id)
    eff_mech = get_effective_locks_for_node(db_session, sem.id, mech_col.id)
    assert eff_cs.total_locks == 2
    assert all(l.inherited_from_ancestor for l in eff_cs.locks)
    assert eff_mech.total_locks == 1

    # 校验：下级系部无权删除校级只读锁定
    with pytest.raises(PermissionError):
        delete_baseline_lock(db_session, lock_id=univ_locks[0].id, operator_org_node_id=cs_dept.id)

    # 3. 端到端联调求解器：计算机系专业课必须严格避让被校级锁定的 ts1，排入 ts2
    task = TeachingTask(
        semester_id=sem.id,
        org_node_id=cs_dept.id,
        course_code="CS301",
        course_name="编译原理",
        course_category="THEORY",
        teacher_id=teacher.id,
        cohort_ids=[cohort_cs.id],
        weekly_sessions=1,
        week_type=0,
        total_students=40,
    )
    db_session.add(task)
    db_session.commit()

    solver_input = load_solver_input_from_db(
        db=db_session, semester_id=sem.id, org_node_id=cs_dept.id, run_mode="SINGLE_DEPT"
    )
    res = CourseScheduleSolver(solver_input).solve()
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert len(res.assignments) == 1
    assert res.assignments[0].timeslot_id == ts2.id

    # 4. 验证将排课方案一键发布为分级锁定基线
    plan = persist_solver_result(db_session, sem.id, cs_dept.id, "系部基线V1", "SINGLE_DEPT", res)
    published_locks = publish_plan_as_baseline(db_session, plan_id=plan.id)
    assert len(published_locks) == 1
    assert published_locks[0].timeslot_id == ts2.id
