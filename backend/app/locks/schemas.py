"""T2.2 分级基线锁定与自由下发数据契约。"""
from typing import List, Optional
from pydantic import BaseModel, Field


class PublicLockItemIn(BaseModel):
    timeslot_id: int
    week_type: int = 0  # 0=全周, 1=单周, 2=双周
    cohort_id: Optional[int] = None
    classroom_id: Optional[int] = None
    teacher_id: Optional[int] = None
    course_name: str
    is_readonly: bool = True


class BaselineLockBatchCreate(BaseModel):
    semester_id: int
    lock_scope_org_id: int
    replace_existing: bool = False
    items: List[PublicLockItemIn] = Field(default_factory=list)


class PublishPlanAsBaselineRequest(BaseModel):
    plan_id: int
    lock_scope_org_id: Optional[int] = None  # 默认使用方案所属 org_node_id
    replace_existing: bool = True


class EffectiveLockOut(BaseModel):
    id: int
    semester_id: int
    lock_scope_org_id: int
    lock_scope_org_name: str
    timeslot_id: int
    week_type: int
    cohort_id: Optional[int]
    classroom_id: Optional[int]
    teacher_id: Optional[int]
    course_name: str
    is_readonly: bool
    inherited_from_ancestor: bool


class EffectiveBaselineLocksOut(BaseModel):
    semester_id: int
    target_org_node_id: int
    total_locks: int
    locks: List[EffectiveLockOut]
