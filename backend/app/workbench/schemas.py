"""T3.2 + T3.3 课表矩阵三重视角与调停课审批流数据契约。"""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class MatrixEntityOption(BaseModel):
    id: int
    label: str
    sub_label: Optional[str] = None


class MatrixCardOut(BaseModel):
    detail_id: int
    task_id: int
    timeslot_id: int
    day_of_week: int
    period_index: int
    classroom_id: int
    room_code: str
    course_code: str
    course_name: str
    course_category: str
    teacher_id: int
    teacher_name: str
    cohort_ids: List[int] = Field(default_factory=list)
    cohort_names: List[str] = Field(default_factory=list)
    week_type: int  # 0全周, 1单周, 2双周
    is_locked: bool = False
    is_manual_adjusted: bool = False
    lock_source: Optional[str] = None


class UnscheduledItemOut(BaseModel):
    task_id: int
    course_code: str
    course_name: str
    teacher_name: str
    weekly_sessions: int
    scheduled_sessions: int
    reason: str


class WorkbenchViewOut(BaseModel):
    plan_id: int
    plan_name: str
    semester_id: int
    org_node_id: int
    run_mode: str
    cohorts: List[MatrixEntityOption] = Field(default_factory=list)
    teachers: List[MatrixEntityOption] = Field(default_factory=list)
    rooms: List[MatrixEntityOption] = Field(default_factory=list)
    cards: List[MatrixCardOut] = Field(default_factory=list)
    unscheduled: List[UnscheduledItemOut] = Field(default_factory=list)


class ChangeRequestCreate(BaseModel):
    plan_id: int
    detail_id: int
    operator_id: int
    change_type: Literal["RESCHEDULE", "SUSPEND", "SUBSTITUTE"]
    target_timeslot_id: Optional[int] = None
    target_classroom_id: Optional[int] = None
    substitute_teacher_id: Optional[int] = None
    reason: str


class ChangeRequestReview(BaseModel):
    reviewer_id: int
    decision: Literal["APPROVED", "REJECTED"]
    review_note: Optional[str] = None


class ChangeRequestOut(BaseModel):
    id: int
    plan_id: int
    operator_id: int
    status: str
    change_type: str
    detail_id: int
    reason: str
    review_note: Optional[str] = None
