"""T2.3 教师禁排与机房黑白名单/借用策略 REST API。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.constraints.schemas import (
    RoomPolicyUpdate,
    RoomRuleCreate,
    RoomRuleOut,
    RoomWithRulesOut,
    TeacherUnavailableBatchUpsert,
    TeacherUnavailableSlotOut,
)
from app.constraints.service import (
    create_room_rule,
    delete_room_rule,
    list_rooms_with_rules,
    list_teacher_unavailable,
    update_room_policy_and_tags,
    upsert_teacher_unavailable,
)
from app.db.session import get_db

router = APIRouter(prefix="/constraints", tags=["constraints"])


@router.get("/teacher-unavailable", response_model=List[TeacherUnavailableSlotOut])
def get_teacher_unavailable_api(
    semester_id: int = Query(...),
    teacher_id: int = Query(...),
    db: Session = Depends(get_db),
):
    return list_teacher_unavailable(db, semester_id=semester_id, teacher_id=teacher_id)


@router.put("/teacher-unavailable", response_model=List[TeacherUnavailableSlotOut])
def put_teacher_unavailable_api(
    payload: TeacherUnavailableBatchUpsert, db: Session = Depends(get_db)
):
    return upsert_teacher_unavailable(db, payload)


@router.get("/rooms", response_model=List[RoomWithRulesOut])
def list_rooms_api(
    owner_org_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    return list_rooms_with_rules(db, owner_org_id=owner_org_id)


@router.patch("/rooms/{room_id}/policy")
def update_room_policy_api(
    room_id: int, payload: RoomPolicyUpdate, db: Session = Depends(get_db)
):
    try:
        room = update_room_policy_and_tags(db, room_id, payload)
        return {
            "id": room.id,
            "room_code": room.room_code,
            "sharing_policy": room.sharing_policy,
            "env_tags": room.env_tags,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/room-rules", response_model=RoomRuleOut)
def create_room_rule_api(payload: RoomRuleCreate, db: Session = Depends(get_db)):
    try:
        return create_room_rule(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/room-rules/{rule_id}")
def delete_room_rule_api(rule_id: int, db: Session = Depends(get_db)):
    try:
        delete_room_rule(db, rule_id)
        return {"deleted_rule_id": rule_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
