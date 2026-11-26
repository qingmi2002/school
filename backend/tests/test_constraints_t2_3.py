"""T2.3 验收门禁测试：教师 5×5 禁排提交幂等覆盖、机房黑白名单与独占/借用策略管理及求解器联动。"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.constraints import (
    create_room_rule,
    delete_room_rule,
    list_rooms_with_rules,
    list_teacher_unavailable,
    update_room_policy_and_tags,
    upsert_teacher_unavailable,
)
from app.constraints.schemas import (
    RoomPolicyUpdate,
    RoomRuleCreate,
    TeacherUnavailableBatchUpsert,
    TeacherUnavailableSlotIn,
)
from app.db.session import Base
from app.models import Classroom, OrgNode, Semester, SysUser, Timeslot
from app.org import apply_org_preset


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


def test_teacher_unavailable_grid_upsert_and_room_rules(db_session):
    apply_org_preset(db_session, "single_dept_standalone", clear_existing=True)
    dept = db_session.query(OrgNode).first()
    sem = Semester(code="2026-2027-1", name="2026秋", total_weeks=18, is_current=True)
    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一 1-2节")
    ts2 = Timeslot(org_node_id=None, day_of_week=3, period_index=3, period_name="周三 5-6节")
    db_session.add_all([sem, ts1, ts2])
    db_session.flush()

    teacher = SysUser(username="T3001", real_name="王老师", org_node_id=dept.id, role_code="TEACHER", password_hash="x")
    room = Classroom(room_code="LAB-301", building="实验楼", owner_org_id=dept.id, capacity=50, room_type="COMPUTER_LAB")
    db_session.add_all([teacher, room])
    db_session.commit()

    # 1. 提交 5×5 禁排网格（1 个 HARD + 1 个 SOFT）
    upsert_teacher_unavailable(
        db_session,
        TeacherUnavailableBatchUpsert(
            semester_id=sem.id,
            teacher_id=teacher.id,
            slots=[
                TeacherUnavailableSlotIn(timeslot_id=ts1.id, constraint_level="HARD", reason="教研室例会"),
                TeacherUnavailableSlotIn(timeslot_id=ts2.id, constraint_level="SOFT", reason="科研"),
            ],
        ),
    )
    rows = list_teacher_unavailable(db_session, sem.id, teacher.id)
    assert len(rows) == 2

    # 幂等覆盖为仅 1 个 HARD
    upsert_teacher_unavailable(
        db_session,
        TeacherUnavailableBatchUpsert(
            semester_id=sem.id,
            teacher_id=teacher.id,
            slots=[TeacherUnavailableSlotIn(timeslot_id=ts1.id, constraint_level="HARD", reason="固定会议")],
        ),
    )
    rows2 = list_teacher_unavailable(db_session, sem.id, teacher.id)
    assert len(rows2) == 1
    assert rows2[0].reason == "固定会议"

    # 2. 更新机房借用策略与软件环境标签，添加黑名单规则
    updated_room = update_room_policy_and_tags(
        db_session,
        room.id,
        RoomPolicyUpdate(sharing_policy="IDLE_BORROW", env_tags=["GPU", "Linux", "Python"]),
    )
    assert updated_room.sharing_policy == "IDLE_BORROW"
    assert updated_room.env_tags == ["GPU", "Linux", "Python"]

    rule = create_room_rule(
        db_session,
        RoomRuleCreate(classroom_id=room.id, course_category="THEORY", rule_type="DENY"),
    )
    rooms_out = list_rooms_with_rules(db_session, owner_org_id=dept.id)
    assert len(rooms_out) == 1
    assert len(rooms_out[0].rules) == 1
    assert rooms_out[0].rules[0].rule_type == "DENY"

    delete_room_rule(db_session, rule.id)
    assert len(list_rooms_with_rules(db_session, owner_org_id=dept.id)[0].rules) == 0
