"""T2.3 教师禁排网格与机房黑白名单/借用策略数据契约。"""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class TeacherUnavailableSlotIn(BaseModel):
    timeslot_id: int
    constraint_level: Literal["HARD", "SOFT"] = "HARD"
    reason: Optional[str] = None
    week_mask: Optional[int] = None


class TeacherUnavailableBatchUpsert(BaseModel):
    semester_id: int
    teacher_id: int
    slots: List[TeacherUnavailableSlotIn] = Field(default_factory=list)


class TeacherUnavailableSlotOut(BaseModel):
    id: int
    semester_id: int
    teacher_id: int
    timeslot_id: int
    constraint_level: str
    reason: Optional[str]
    week_mask: Optional[int] = None


class RoomPolicyUpdate(BaseModel):
    sharing_policy: Literal["EXCLUSIVE", "IDLE_BORROW", "PUBLIC_POOL"]
    env_tags: List[str] = Field(default_factory=list)
    capacity: Optional[int] = None


class RoomRuleCreate(BaseModel):
    classroom_id: int
    course_code: Optional[str] = None
    course_category: Optional[Literal["THEORY", "LAB", "MIXED"]] = None
    rule_type: Literal["ALLOW", "DENY"]
    priority: int = 10


class RoomRuleOut(BaseModel):
    id: int
    classroom_id: int
    course_code: Optional[str]
    course_category: Optional[str]
    rule_type: str
    priority: int


class RoomWithRulesOut(BaseModel):
    id: int
    room_code: str
    building: str
    owner_org_id: int
    capacity: int
    room_type: str
    env_tags: List[str]
    sharing_policy: str
    rules: List[RoomRuleOut] = Field(default_factory=list)
