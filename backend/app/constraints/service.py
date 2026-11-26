"""T2.3 教师禁排采集与机房黑白名单/借用策略管理服务。"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.constraints.schemas import (
    RoomPolicyUpdate,
    RoomRuleCreate,
    RoomRuleOut,
    RoomWithRulesOut,
    TeacherUnavailableBatchUpsert,
)
from app.models import Classroom, RoomCourseRule, TeacherUnavailable


def upsert_teacher_unavailable(
    db: Session, payload: TeacherUnavailableBatchUpsert
) -> List[TeacherUnavailable]:
    """幂等覆盖某教师在指定学期的 5×5 禁排网格。"""
    db.query(TeacherUnavailable).filter(
        TeacherUnavailable.semester_id == payload.semester_id,
        TeacherUnavailable.teacher_id == payload.teacher_id,
    ).delete()

    created: List[TeacherUnavailable] = []
    for item in payload.slots:
        row = TeacherUnavailable(
            semester_id=payload.semester_id,
            teacher_id=payload.teacher_id,
            timeslot_id=item.timeslot_id,
            constraint_level=item.constraint_level,
            reason=item.reason,
        )
        db.add(row)
        created.append(row)

    db.commit()
    for row in created:
        db.refresh(row)
    return created


def list_teacher_unavailable(
    db: Session, semester_id: int, teacher_id: int
) -> List[TeacherUnavailable]:
    return (
        db.query(TeacherUnavailable)
        .filter(
            TeacherUnavailable.semester_id == semester_id,
            TeacherUnavailable.teacher_id == teacher_id,
        )
        .order_by(TeacherUnavailable.timeslot_id)
        .all()
    )


def update_room_policy_and_tags(
    db: Session, room_id: int, payload: RoomPolicyUpdate
) -> Classroom:
    room = db.query(Classroom).filter(Classroom.id == room_id).first()
    if room is None:
        raise ValueError(f"教室/机房 id={room_id} 不存在")
    room.sharing_policy = payload.sharing_policy
    room.env_tags = sorted({t.strip() for t in payload.env_tags if t.strip()})
    if payload.capacity is not None and payload.capacity > 0:
        room.capacity = payload.capacity
    db.commit()
    db.refresh(room)
    return room


def create_room_rule(db: Session, payload: RoomRuleCreate) -> RoomCourseRule:
    room = db.query(Classroom).filter(Classroom.id == payload.classroom_id).first()
    if room is None:
        raise ValueError(f"教室/机房 id={payload.classroom_id} 不存在")
    if not payload.course_code and not payload.course_category:
        raise ValueError("课程代码与课程类型至少需填写一项")

    rule = RoomCourseRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def delete_room_rule(db: Session, rule_id: int) -> None:
    rule = db.query(RoomCourseRule).filter(RoomCourseRule.id == rule_id).first()
    if rule is None:
        raise ValueError(f"机房规则 id={rule_id} 不存在")
    db.delete(rule)
    db.commit()


def list_rooms_with_rules(
    db: Session, owner_org_id: Optional[int] = None
) -> List[RoomWithRulesOut]:
    q = db.query(Classroom).filter(Classroom.is_active.is_(True))
    if owner_org_id is not None:
        q = q.filter(Classroom.owner_org_id == owner_org_id)
    rooms = q.order_by(Classroom.room_code).all()
    room_ids = [r.id for r in rooms]
    rules = (
        db.query(RoomCourseRule)
        .filter(RoomCourseRule.classroom_id.in_(room_ids))
        .order_by(RoomCourseRule.priority)
        .all()
        if room_ids
        else []
    )
    rules_by_room: dict[int, List[RoomRuleOut]] = {}
    for rl in rules:
        rules_by_room.setdefault(rl.classroom_id, []).append(
            RoomRuleOut(
                id=rl.id,
                classroom_id=rl.classroom_id,
                course_code=rl.course_code,
                course_category=rl.course_category,
                rule_type=rl.rule_type,
                priority=rl.priority,
            )
        )

    return [
        RoomWithRulesOut(
            id=r.id,
            room_code=r.room_code,
            building=r.building,
            owner_org_id=r.owner_org_id,
            capacity=r.capacity,
            room_type=r.room_type,
            env_tags=list(r.env_tags or []),
            sharing_policy=r.sharing_policy,
            rules=rules_by_room.get(r.id, []),
        )
        for r in rooms
    ]
