"""T2.1 多级自由调整组织树、横向资源授权矩阵与节点级作息覆写数据契约。"""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class OrgFlagsUpdate(BaseModel):
    is_scheduling_unit: Optional[bool] = None
    is_public_provider: Optional[bool] = None
    has_student_cohort: Optional[bool] = None
    has_room_pool: Optional[bool] = None
    is_campus_boundary: Optional[bool] = None
    is_summary_node: Optional[bool] = None
    allow_custom_timeslot: Optional[bool] = None


class OrgNodeCreate(BaseModel):
    parent_id: Optional[int] = None
    node_code: str
    node_name: str
    node_type_code: str
    is_scheduling_unit: bool = False
    is_public_provider: bool = False
    has_student_cohort: bool = False
    has_room_pool: bool = False
    is_campus_boundary: bool = False
    is_summary_node: bool = False
    allow_custom_timeslot: bool = False


class OrgNodeOut(BaseModel):
    id: int
    parent_id: Optional[int]
    node_code: str
    node_name: str
    node_type_code: str
    tree_path: str
    depth: int
    is_scheduling_unit: bool
    is_public_provider: bool
    has_student_cohort: bool
    has_room_pool: bool
    is_campus_boundary: bool
    is_summary_node: bool
    allow_custom_timeslot: bool
    resolved_campus_id: Optional[int] = None
    children: List["OrgNodeOut"] = Field(default_factory=list)


class ResourceGrantUpsert(BaseModel):
    granter_org_id: int
    grantee_org_id: int
    semester_id: Optional[int] = None
    resource_type: Literal["ROOM_POOL", "TEACHER", "PUBLIC_COURSE"]
    grant_mode: Literal["FULL", "IDLE_ONLY", "APPROVAL_REQUIRED"] = "IDLE_ONLY"
    is_active: bool = True
    remark: Optional[str] = None


class ResourceAccessCheckOut(BaseModel):
    allowed: bool
    access_via: Literal["SELF", "ANCESTOR_INHERIT", "LATERAL_GRANT", "DENIED"]
    grant_mode: Optional[str] = None
    reason: str


class TimeslotItemIn(BaseModel):
    day_of_week: int
    period_index: int
    period_name: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_evening: bool = False


class TimeslotItemOut(TimeslotItemIn):
    id: int
    org_node_id: Optional[int] = None


class EffectiveTimeslotsOut(BaseModel):
    target_org_node_id: int
    source_org_node_id: Optional[int]  # None 表示继承自全校默认时间片
    inherited: bool
    timeslots: List[TimeslotItemOut]
