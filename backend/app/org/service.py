"""
T2.1 多级自由调整组织树与横向资源授权核心服务
- 支持任意深度节点 CRUD 与 5 大正交开关动态切换
- 支持 7 套架构（单院系独立模式 + 6 类高校体制）一键初始化
- 支持向上继承与 org_resource_grant 横向资源借用校验
- 支持节点级作息时间片自由覆写与自动向上继承
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.org_presets import (
    NODE_TYPE_DICTIONARY,
    ORG_ARCHETYPE_PRESETS,
    resolve_campus_boundary_id,
)
from app.models import NodeType, OrgNode, OrgResourceGrant, Timeslot
from app.org.schemas import (
    EffectiveTimeslotsOut,
    OrgFlagsUpdate,
    OrgNodeCreate,
    OrgNodeOut,
    ResourceAccessCheckOut,
    ResourceGrantUpsert,
    TimeslotItemIn,
    TimeslotItemOut,
)


def ensure_node_type_dictionary(db: Session) -> None:
    existing = {r.code for r in db.query(NodeType.code).all()}
    for item in NODE_TYPE_DICTIONARY:
        if item["code"] not in existing:
            db.add(NodeType(**item))
    db.flush()


def create_org_node(db: Session, payload: OrgNodeCreate) -> OrgNode:
    ensure_node_type_dictionary(db)
    parent: Optional[OrgNode] = None
    if payload.parent_id is not None:
        parent = db.query(OrgNode).filter(OrgNode.id == payload.parent_id).first()
        if parent is None:
            raise ValueError(f"父组织节点 id={payload.parent_id} 不存在")

    node = OrgNode(
        parent_id=payload.parent_id,
        node_code=payload.node_code,
        node_name=payload.node_name,
        node_type_code=payload.node_type_code,
        tree_path="/pending/",
        depth=(parent.depth + 1) if parent else 1,
        is_scheduling_unit=payload.is_scheduling_unit,
        is_public_provider=payload.is_public_provider,
        has_student_cohort=payload.has_student_cohort,
        has_room_pool=payload.has_room_pool,
        is_campus_boundary=payload.is_campus_boundary,
        is_summary_node=payload.is_summary_node,
        allow_custom_timeslot=payload.allow_custom_timeslot,
    )
    db.add(node)
    db.flush()
    node.tree_path = f"{parent.tree_path}{node.id}/" if parent else f"/{node.id}/"
    db.commit()
    db.refresh(node)
    return node


def update_org_flags(db: Session, node_id: int, flags: OrgFlagsUpdate) -> OrgNode:
    node = db.query(OrgNode).filter(OrgNode.id == node_id).first()
    if node is None:
        raise ValueError(f"组织节点 id={node_id} 不存在")
    for field_name, val in flags.model_dump(exclude_none=True).items():
        setattr(node, field_name, val)
    db.commit()
    db.refresh(node)
    return node


def apply_org_preset(db: Session, preset_key: str, clear_existing: bool = False) -> List[OrgNode]:
    if preset_key not in ORG_ARCHETYPE_PRESETS:
        raise ValueError(f"未知组织架构预设：{preset_key}")

    ensure_node_type_dictionary(db)

    if clear_existing:
        # 仅在演示/初始化空库时清理旧节点（按深度倒序删除满足 RESTRICT 外键）
        db.query(OrgResourceGrant).delete()
        old_nodes = db.query(OrgNode).order_by(OrgNode.depth.desc()).all()
        for n in old_nodes:
            db.delete(n)
        db.flush()

    preset = ORG_ARCHETYPE_PRESETS[preset_key]
    created_by_code: Dict[str, OrgNode] = {}
    created_list: List[OrgNode] = []

    for item in preset["nodes"]:
        parent_node = created_by_code.get(item["parent"]) if item["parent"] else None
        flags = item.get("flags", {})
        node = OrgNode(
            parent_id=parent_node.id if parent_node else None,
            node_code=item["code"],
            node_name=item["name"],
            node_type_code=item["type"],
            tree_path="/pending/",
            depth=(parent_node.depth + 1) if parent_node else 1,
            is_scheduling_unit=flags.get("is_scheduling_unit", False),
            is_public_provider=flags.get("is_public_provider", False),
            has_student_cohort=flags.get("has_student_cohort", False),
            has_room_pool=flags.get("has_room_pool", False),
            is_campus_boundary=flags.get("is_campus_boundary", False),
            is_summary_node=flags.get("is_summary_node", False),
            allow_custom_timeslot=flags.get("allow_custom_timeslot", False),
        )
        db.add(node)
        db.flush()
        node.tree_path = f"{parent_node.tree_path}{node.id}/" if parent_node else f"/{node.id}/"
        created_by_code[item["code"]] = node
        created_list.append(node)

    db.commit()
    return created_list


def build_org_tree(db: Session) -> List[OrgNodeOut]:
    nodes = db.query(OrgNode).filter(OrgNode.is_active.is_(True)).order_by(OrgNode.depth, OrgNode.id).all()
    node_map = {n.id: n for n in nodes}
    out_map: Dict[int, OrgNodeOut] = {}

    for n in nodes:
        out_map[n.id] = OrgNodeOut(
            id=n.id,
            parent_id=n.parent_id,
            node_code=n.node_code,
            node_name=n.node_name,
            node_type_code=n.node_type_code,
            tree_path=n.tree_path,
            depth=n.depth,
            is_scheduling_unit=n.is_scheduling_unit,
            is_public_provider=n.is_public_provider,
            has_student_cohort=n.has_student_cohort,
            has_room_pool=n.has_room_pool,
            is_campus_boundary=n.is_campus_boundary,
            is_summary_node=n.is_summary_node,
            allow_custom_timeslot=n.allow_custom_timeslot,
            resolved_campus_id=resolve_campus_boundary_id(node_map, n.id),
            children=[],
        )

    roots: List[OrgNodeOut] = []
    for n in nodes:
        dto = out_map[n.id]
        if n.parent_id is not None and n.parent_id in out_map:
            out_map[n.parent_id].children.append(dto)
        else:
            roots.append(dto)
    return roots


def upsert_resource_grant(db: Session, payload: ResourceGrantUpsert) -> OrgResourceGrant:
    if payload.granter_org_id == payload.grantee_org_id:
        raise ValueError("资源授权方与被授权方不能为同一组织节点")

    existing = (
        db.query(OrgResourceGrant)
        .filter(
            OrgResourceGrant.granter_org_id == payload.granter_org_id,
            OrgResourceGrant.grantee_org_id == payload.grantee_org_id,
            OrgResourceGrant.resource_type == payload.resource_type,
            OrgResourceGrant.semester_id == payload.semester_id,
        )
        .first()
    )
    if existing:
        existing.grant_mode = payload.grant_mode
        existing.is_active = payload.is_active
        existing.remark = payload.remark
        db.commit()
        db.refresh(existing)
        return existing

    grant = OrgResourceGrant(**payload.model_dump())
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def authorize_resource_access(
    db: Session,
    requester_org_id: int,
    resource_owner_org_id: int,
    resource_type: str = "ROOM_POOL",
    semester_id: Optional[int] = None,
) -> ResourceAccessCheckOut:
    """
    多级资源访问与横向借用授权中间件核心判定：
    1. 自身直属资源 -> 允许 (SELF)
    2. 沿 tree_path 向上继承上级共享池（如学院机房/学校公共教学楼） -> 允许 (ANCESTOR_INHERIT)
    3. 存在有效的 org_resource_grant 横向授权 -> 允许 (LATERAL_GRANT)
    4. 其余跨组织访问 -> 拒绝 (DENIED)
    """
    if requester_org_id == resource_owner_org_id:
        return ResourceAccessCheckOut(
            allowed=True, access_via="SELF", grant_mode="FULL", reason="本组织直属资源"
        )

    req_node = db.query(OrgNode).filter(OrgNode.id == requester_org_id).first()
    owner_node = db.query(OrgNode).filter(OrgNode.id == resource_owner_org_id).first()
    if req_node is None or owner_node is None:
        return ResourceAccessCheckOut(
            allowed=False, access_via="DENIED", reason="请求方或资源归属组织节点不存在"
        )

    # 向上继承判定：owner 是 requester 的祖先且具备对应资源池能力
    if req_node.tree_path.startswith(owner_node.tree_path):
        if resource_type == "ROOM_POOL" and owner_node.has_room_pool:
            return ResourceAccessCheckOut(
                allowed=True,
                access_via="ANCESTOR_INHERIT",
                grant_mode="IDLE_ONLY",
                reason=f"沿组织树向上继承上级节点【{owner_node.node_name}】的共享场地池",
            )
        if resource_type == "PUBLIC_COURSE" and owner_node.is_public_provider:
            return ResourceAccessCheckOut(
                allowed=True,
                access_via="ANCESTOR_INHERIT",
                grant_mode="FULL",
                reason=f"承接上级公共课输出节点【{owner_node.node_name}】的基线",
            )

    # 横向资源授权矩阵判定（优先匹配指定学期，其次匹配全局 semester_id IS NULL）
    grants = (
        db.query(OrgResourceGrant)
        .filter(
            OrgResourceGrant.granter_org_id == resource_owner_org_id,
            OrgResourceGrant.grantee_org_id == requester_org_id,
            OrgResourceGrant.resource_type == resource_type,
            OrgResourceGrant.is_active.is_(True),
        )
        .all()
    )
    matched = next((g for g in grants if g.semester_id == semester_id), None) or next(
        (g for g in grants if g.semester_id is None), None
    )
    if matched:
        return ResourceAccessCheckOut(
            allowed=True,
            access_via="LATERAL_GRANT",
            grant_mode=matched.grant_mode,
            reason=f"已获【{owner_node.node_name}】横向资源授权（模式：{matched.grant_mode}）",
        )

    return ResourceAccessCheckOut(
        allowed=False,
        access_via="DENIED",
        reason=f"无权借用【{owner_node.node_name}】的 {resource_type} 资源，请先在横向授权矩阵中开通",
    )


def upsert_node_timeslots(
    db: Session,
    org_node_id: Optional[int],
    items: List[TimeslotItemIn],
) -> List[Timeslot]:
    if org_node_id is not None:
        node = db.query(OrgNode).filter(OrgNode.id == org_node_id).first()
        if node is None:
            raise ValueError(f"组织节点 id={org_node_id} 不存在")
        if not node.allow_custom_timeslot:
            node.allow_custom_timeslot = True

    db.query(Timeslot).filter(Timeslot.org_node_id == org_node_id).delete()
    created = []
    for item in items:
        ts = Timeslot(org_node_id=org_node_id, **item.model_dump())
        db.add(ts)
        created.append(ts)
    db.commit()
    for ts in created:
        db.refresh(ts)
    return created


def get_effective_timeslots(db: Session, org_node_id: int) -> EffectiveTimeslotsOut:
    """查询节点生效作息：优先本节点自定义覆写 -> 沿父链向上回溯 -> 全校默认(org_node_id IS NULL)。"""
    node = db.query(OrgNode).filter(OrgNode.id == org_node_id).first()
    if node is None:
        raise ValueError(f"组织节点 id={org_node_id} 不存在")

    # 按 tree_path 从当前节点向上溯源（如 /1/2/5/ -> [5, 2, 1]）
    ancestor_ids = [int(x) for x in node.tree_path.strip("/").split("/") if x]
    ancestor_ids.reverse()

    for idx, nid in enumerate(ancestor_ids):
        rows = (
            db.query(Timeslot)
            .filter(Timeslot.org_node_id == nid)
            .order_by(Timeslot.day_of_week, Timeslot.period_index)
            .all()
        )
        if rows:
            return EffectiveTimeslotsOut(
                target_org_node_id=org_node_id,
                source_org_node_id=nid,
                inherited=(idx > 0),
                timeslots=[
                    TimeslotItemOut(
                        id=r.id,
                        org_node_id=r.org_node_id,
                        day_of_week=r.day_of_week,
                        period_index=r.period_index,
                        period_name=r.period_name,
                        start_time=r.start_time,
                        end_time=r.end_time,
                        is_evening=r.is_evening,
                    )
                    for r in rows
                ],
            )

    default_rows = (
        db.query(Timeslot)
        .filter(Timeslot.org_node_id.is_(None))
        .order_by(Timeslot.day_of_week, Timeslot.period_index)
        .all()
    )
    return EffectiveTimeslotsOut(
        target_org_node_id=org_node_id,
        source_org_node_id=None,
        inherited=True,
        timeslots=[
            TimeslotItemOut(
                id=r.id,
                org_node_id=r.org_node_id,
                day_of_week=r.day_of_week,
                period_index=r.period_index,
                period_name=r.period_name,
                start_time=r.start_time,
                end_time=r.end_time,
                is_evening=r.is_evening,
            )
            for r in default_rows
        ],
    )
