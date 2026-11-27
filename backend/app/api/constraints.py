"""T2.3 + V1.5 教师自主禁排填报（含分级权限与窗口开关）与机房黑白名单/借用策略 REST API。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import get_optional_current_user
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
from app.models import OrgNode, SystemConfig, SysUser
from app.org.rbac import SCHEDULER_ROLES

router = APIRouter(prefix="/constraints", tags=["constraints"])


class UnavailWindowPayload(BaseModel):
    is_open: bool = True


def _is_unavail_window_open(db: Session) -> bool:
    row = db.query(SystemConfig).filter(SystemConfig.config_key == "teacher_unavail_open").first()
    if row is None:
        return True
    if isinstance(row.config_value, dict):
        return bool(row.config_value.get("is_open", True))
    return str(row.config_value).lower() not in ("false", "0", "closed")


def _enforce_teacher_unavail_access(
    db: Session,
    current_user: Optional[SysUser],
    target_teacher_id: int,
    is_write: bool,
) -> None:
    if current_user is None:
        return
    if current_user.role_code in SCHEDULER_ROLES:
        return
    if current_user.role_code == "TEACHING_LEAD":
        if target_teacher_id == current_user.id:
            return
        lead_org = db.query(OrgNode).filter(OrgNode.id == current_user.org_node_id).first()
        target = db.query(SysUser).filter(SysUser.id == target_teacher_id).first()
        if not target or not lead_org:
            raise HTTPException(status_code=404, detail="目标教师不存在")
        target_org = db.query(OrgNode).filter(OrgNode.id == target.org_node_id).first()
        if not target_org or not target_org.tree_path.startswith(lead_org.tree_path):
            raise HTTPException(status_code=403, detail="教研室主任仅可管理本教研室/本系教师的禁排填报")
        return
    if current_user.role_code == "TEACHER":
        if target_teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="普通教师仅可查看或填报本人的禁排需求")
        if is_write and not _is_unavail_window_open(db):
            raise HTTPException(status_code=403, detail="管理员已关闭本学期教师禁排自助填报窗口")
        return
    raise HTTPException(status_code=403, detail="当前角色无权访问教师禁排填报")


@router.get("/teacher-unavail-window")
def get_teacher_unavail_window(db: Session = Depends(get_db)):
    return {"is_open": _is_unavail_window_open(db)}


@router.put("/teacher-unavail-window")
def set_teacher_unavail_window(
    payload: UnavailWindowPayload,
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    if current_user is not None and current_user.role_code not in SCHEDULER_ROLES:
        raise HTTPException(status_code=403, detail="仅排课管理员可开关教师禁排填报窗口")
    row = db.query(SystemConfig).filter(SystemConfig.config_key == "teacher_unavail_open").first()
    val = {"is_open": bool(payload.is_open)}
    if row is None:
        db.add(SystemConfig(config_key="teacher_unavail_open", config_value=val))
    else:
        row.config_value = val
    db.commit()
    return {"is_open": payload.is_open}


@router.get("/teacher-unavailable", response_model=List[TeacherUnavailableSlotOut])
def get_teacher_unavailable_api(
    semester_id: int = Query(...),
    teacher_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    _enforce_teacher_unavail_access(db, current_user, teacher_id, is_write=False)
    return list_teacher_unavailable(db, semester_id=semester_id, teacher_id=teacher_id)


@router.put("/teacher-unavailable", response_model=List[TeacherUnavailableSlotOut])
def put_teacher_unavailable_api(
    payload: TeacherUnavailableBatchUpsert,
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    _enforce_teacher_unavail_access(db, current_user, payload.teacher_id, is_write=True)
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
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/room-rules/{rule_id}")
def delete_room_rule_api(rule_id: int, db: Session = Depends(get_db)):
    if not delete_room_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"deleted": True, "rule_id": rule_id}
