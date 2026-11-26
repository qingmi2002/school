"""T3.2 + T3.3 验收门禁测试：三重视角工作台聚合（含灰色公共课锁定与未排诊断）及调停课审批流闭环。"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.locks import upsert_baseline_locks
from app.locks.schemas import BaselineLockBatchCreate, PublicLockItemIn
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
from app.org import apply_org_preset
from app.workbench import (
    create_change_request,
    get_workbench_view,
    list_change_requests,
    review_change_request,
)
from app.workbench.schemas import ChangeRequestCreate, ChangeRequestReview


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


def test_workbench_view_and_change_request_approval(db_session):
    apply_org_preset(db_session, "school_college_dept", clear_existing=True)
    univ = db_session.query(OrgNode).filter(OrgNode.node_code == "UNIV").first()
    dept = db_session.query(OrgNode).filter(OrgNode.node_code == "CS_DEPT").first()

    sem = Semester(code="2026-2027-1", name="2026秋", total_weeks=18, is_current=True)
    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一 1-2节")
    ts2 = Timeslot(org_node_id=None, day_of_week=2, period_index=1, period_name="周二 1-2节")
    ts3 = Timeslot(org_node_id=None, day_of_week=3, period_index=2, period_name="周三 3-4节")
    db_session.add_all([sem, ts1, ts2, ts3])
    db_session.flush()

    cohort = StudentCohort(cohort_code="CS2401", cohort_name="计科2401", org_node_id=dept.id, grade_year=2024, student_count=40)
    teacher = SysUser(username="T6001", real_name="刘老师", org_node_id=dept.id, role_code="TEACHER", password_hash="x")
    admin = SysUser(username="A6001", real_name="教务员", org_node_id=dept.id, role_code="DEPT_SCHEDULER", password_hash="x")
    room = Classroom(room_code="LAB-101", building="信息楼", owner_org_id=dept.id, capacity=60, room_type="COMPUTER_LAB")
    db_session.add_all([cohort, teacher, admin, room])
    db_session.flush()

    upsert_baseline_locks(
        db_session,
        BaselineLockBatchCreate(
            semester_id=sem.id,
            lock_scope_org_id=univ.id,
            items=[PublicLockItemIn(timeslot_id=ts1.id, cohort_id=cohort.id, course_name="大学英语")],
        ),
    )

    task_ok = TeachingTask(semester_id=sem.id, org_node_id=dept.id, course_code="CS101", course_name="数据结构", course_category="LAB", teacher_id=teacher.id, cohort_ids=[cohort.id], weekly_sessions=1, week_type=0, total_students=40)
    task_unsched = TeachingTask(semester_id=sem.id, org_node_id=dept.id, course_code="CS999", course_name="GPU实训", course_category="LAB", teacher_id=teacher.id, cohort_ids=[cohort.id], weekly_sessions=1, week_type=0, total_students=40)
    plan = SchedulePlan(semester_id=sem.id, org_node_id=dept.id, plan_name="计科V1", version_tag="V1", run_mode="SINGLE_DEPT")
    db_session.add_all([task_ok, task_unsched, plan])
    db_session.flush()

    det = ScheduleDetail(plan_id=plan.id, task_id=task_ok.id, timeslot_id=ts2.id, classroom_id=room.id, week_type=0)
    db_session.add(det)
    db_session.commit()

    view = get_workbench_view(db_session, plan.id)
    assert len(view.cards) == 2
    assert any(c.is_locked and c.course_name == "大学英语" for c in view.cards)
    assert len(view.unscheduled) == 1
    assert view.unscheduled[0].course_code == "CS999"

    req = create_change_request(
        db_session,
        ChangeRequestCreate(
            plan_id=plan.id,
            detail_id=det.id,
            operator_id=teacher.id,
            change_type="RESCHEDULE",
            target_timeslot_id=ts3.id,
            target_classroom_id=room.id,
            reason="外出学术会议调课",
        ),
    )
    assert req.status == "PENDING"
    assert len(list_change_requests(db_session, plan.id)) == 1

    approved = review_change_request(
        db_session,
        req.id,
        ChangeRequestReview(reviewer_id=admin.id, decision="APPROVED", review_note="同意调课"),
    )
    assert approved.status == "APPROVED"
    db_session.refresh(det)
    assert det.timeslot_id == ts3.id
    assert det.is_manual_adjusted is True
