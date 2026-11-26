"""T3.1 毫秒级红绿灯实时冲突校验与全校/院系一键体检数据契约。"""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class DragCheckRequest(BaseModel):
    plan_id: int
    detail_id: int
    target_timeslot_id: int
    target_classroom_id: int
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = "SCHOOL_WIDE"


class SlotLightResult(BaseModel):
    target_timeslot_id: int
    target_classroom_id: int
    light: Literal["GREEN", "YELLOW", "RED"]
    allowed: bool
    elapsed_ms: float
    hard_conflicts: List[str] = Field(default_factory=list)
    soft_warnings: List[str] = Field(default_factory=list)


class MatrixLightsRequest(BaseModel):
    plan_id: int
    detail_id: int
    target_classroom_id: int
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = "SCHOOL_WIDE"


class MatrixLightsResponse(BaseModel):
    plan_id: int
    detail_id: int
    target_classroom_id: int
    elapsed_ms: float
    slots: Dict[int, SlotLightResult]  # key = timeslot_id


class HealthCheckIssue(BaseModel):
    issue_type: Literal[
        "ROOM_CONFLICT",
        "TEACHER_CROSS_DEPT_CONFLICT",
        "COHORT_CONFLICT",
        "CROSS_CAMPUS_COMMUTE",
        "PUBLIC_LOCK_VIOLATION",
        "ROOM_RULE_VIOLATION",
    ]
    severity: Literal["ERROR", "WARNING"] = "ERROR"
    message: str
    detail_ids: List[int] = Field(default_factory=list)


class HealthCheckReport(BaseModel):
    semester_id: int
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"]
    org_node_id: Optional[int] = None
    passed: bool
    total_checked_sessions: int
    conflict_count: int
    elapsed_ms: float
    issues: List[HealthCheckIssue] = Field(default_factory=list)
