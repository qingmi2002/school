"""组织机构自定义 CRUD（增删改节点、动态开关、预设初始化、横向借用与节点作息）REST API。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.org_presets import NODE_TYPE_DICTIONARY, ORG_ARCHETYPE_PRESETS
from app.db.session import get_db
from app.models import OrgNode
from app.org.schemas import (
    EffectiveTimeslotsOut,
    OrgFlagsUpdate,
    OrgNodeCreate,
    OrgNodeOut,
    ResourceAccessCheckOut,
    ResourceGrantUpsert,
    TimeslotItemIn,
)
from app.org.service import (
    apply_org_preset,
    authorize_resource_access,
    build_org_tree,
    create_org_node,
    get_effective_timeslots,
    update_org_flags,
    upsert_node_timeslots,
    upsert_resource_grant,
)

router = APIRouter(prefix="/org", tags=["org-tree"])


class OrgNodeRename(BaseModel):
    node_name: str
    node_type_code: Optional[str] = None


@router.get("/node-types")
def list_node_types():
    return NODE_TYPE_DICTIONARY


@router.get("/presets")
def list_org_presets():
    return {
        k: {"name": v["name"], "description": v["description"], "node_count": len(v["nodes"])}
        for k, v in ORG_ARCHETYPE_PRESETS.items()
    }


@router.post("/presets/{preset_key}/apply")
def apply_preset_api(preset_key: str, clear_existing: bool = Query(False), db: Session = Depends(get_db)):
    try:
        nodes = apply_org_preset(db, preset_key=preset_key, clear_existing=clear_existing)
        return {"preset": preset_key, "created_count": len(nodes)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tree", response_model=List[OrgNodeOut])
def get_org_tree_api(db: Session = Depends(get_db)):
    return build_org_tree(db)


@router.post("/nodes")
def create_org_node_api(payload: OrgNodeCreate, db: Session = Depends(get_db)):
    try:
        node = create_org_node(db, payload)
        return {"id": node.id, "node_code": node.node_code, "node_name": node.node_name, "tree_path": node.tree_path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/nodes/{node_id}")
def rename_org_node_api(node_id: int, payload: OrgNodeRename, db: Session = Depends(get_db)):
    node = db.query(OrgNode).filter(OrgNode.id == node_id).first()
    if node is None:
        raise HTTPException(status_code=404, detail="组织节点不存在")
    node.node_name = payload.node_name
    if payload.node_type_code:
        node.node_type_code = payload.node_type_code
    db.commit()
    return {"id": node.id, "node_name": node.node_name, "node_type_code": node.node_type_code}


@router.delete("/nodes/{node_id}")
def delete_org_node_api(node_id: int, db: Session = Depends(get_db)):
    node = db.query(OrgNode).filter(OrgNode.id == node_id).first()
    if node is None:
        raise HTTPException(status_code=404, detail="组织节点不存在")
    has_children = db.query(OrgNode).filter(OrgNode.parent_id == node_id, OrgNode.is_active.is_(True)).count() > 0
    if has_children:
        raise HTTPException(status_code=400, detail="该节点下仍有子组织，请先删除子组织")
    node.is_active = False
    db.commit()
    return {"deleted_id": node_id}


@router.patch("/nodes/{node_id}/flags")
def update_org_flags_api(node_id: int, payload: OrgFlagsUpdate, db: Session = Depends(get_db)):
    try:
        node = update_org_flags(db, node_id, payload)
        return {"id": node.id, "node_name": node.node_name, "is_scheduling_unit": node.is_scheduling_unit}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/grants")
def upsert_resource_grant_api(payload: ResourceGrantUpsert, db: Session = Depends(get_db)):
    try:
        g = upsert_resource_grant(db, payload)
        return {"id": g.id, "grant_mode": g.grant_mode, "is_active": g.is_active}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/grants/check", response_model=ResourceAccessCheckOut)
def check_resource_access_api(
    requester_org_id: int,
    resource_owner_org_id: int,
    resource_type: str = "ROOM_POOL",
    semester_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return authorize_resource_access(
        db=db,
        requester_org_id=requester_org_id,
        resource_owner_org_id=resource_owner_org_id,
        resource_type=resource_type,
        semester_id=semester_id,
    )


@router.put("/nodes/{node_id}/timeslots")
def set_node_timeslots_api(node_id: int, items: List[TimeslotItemIn], db: Session = Depends(get_db)):
    try:
        rows = upsert_node_timeslots(db, org_node_id=node_id, items=items)
        return {"org_node_id": node_id, "count": len(rows)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/nodes/{node_id}/effective-timeslots", response_model=EffectiveTimeslotsOut)
def get_effective_timeslots_api(node_id: int, db: Session = Depends(get_db)):
    try:
        return get_effective_timeslots(db, org_node_id=node_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
