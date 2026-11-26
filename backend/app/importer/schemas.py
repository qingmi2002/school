"""T1.3 双模式 Excel 导入网关数据契约与可配置列映射。"""
from typing import Dict, List, Literal, Optional, Set, Tuple
from pydantic import BaseModel, Field


DEFAULT_COLUMN_ALIASES: Dict[str, List[str]] = {
    "course_code": ["课程代码", "课号", "course_code"],
    "course_name": ["课程名称", "课名", "course_name"],
    "course_category": ["课程类型", "课程性质", "course_category"],
    "teacher_username": ["教师工号", "任课教师工号", "工号", "teacher_username"],
    "cohort_codes": ["行政班代码", "合班班级", "班级代码", "cohort_codes"],
    "weekly_sessions": ["周大课次数", "周学时次数", "weekly_sessions"],
    "week_type": ["单双周", "周次类型", "week_type"],
    "total_students": ["合班人数", "学生人数", "人数", "total_students"],
    "required_env_tags": ["软件环境标签", "机房标签", "required_env_tags"],
    # 模式 B（预排课表）扩展列
    "day_of_week": ["星期", "周几", "day_of_week"],
    "period_index": ["节次", "大节", "period_index"],
    "room_code": ["教室编号", "机房编号", "教室", "room_code"],
}


class ExistingOccupancy(BaseModel):
    """已存在于全校/系部数据库中的占用记录（用于模式 B 碰撞检测）。"""
    day_of_week: int
    period_index: int
    week_type: int = 0
    room_code: Optional[str] = None
    teacher_username: Optional[str] = None
    cohort_code: Optional[str] = None
    source_label: str = "全校已有课表"


class RoomMeta(BaseModel):
    room_code: str
    capacity: int
    room_type: str = "NORMAL"
    env_tags: List[str] = Field(default_factory=list)
    allow_course_codes: List[str] = Field(default_factory=list)
    allow_categories: List[str] = Field(default_factory=list)
    deny_course_codes: List[str] = Field(default_factory=list)
    deny_categories: List[str] = Field(default_factory=list)


class ImportContext(BaseModel):
    """校验上下文（与 ORM 解耦，支持单院系独立或全校级碰撞检测）。"""
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = "SCHOOL_WIDE"
    valid_teachers: Set[str] = Field(default_factory=set)
    valid_cohorts: Set[str] = Field(default_factory=set)
    rooms: Dict[str, RoomMeta] = Field(default_factory=dict)
    # 教师硬禁排：(teacher_username, day_of_week, period_index)
    teacher_hard_unavailable: Set[Tuple[str, int, int]] = Field(default_factory=set)
    existing_occupancies: List[ExistingOccupancy] = Field(default_factory=list)
    column_aliases: Dict[str, List[str]] = Field(default_factory=lambda: DEFAULT_COLUMN_ALIASES)


class ParsedTaskRow(BaseModel):
    row_number: int
    course_code: str
    course_name: str
    course_category: Literal["THEORY", "LAB", "MIXED"]
    teacher_username: str
    cohort_codes: List[str]
    weekly_sessions: int
    week_type: int
    total_students: int
    required_env_tags: List[str] = Field(default_factory=list)


class ParsedPreScheduleRow(ParsedTaskRow):
    day_of_week: int
    period_index: int
    room_code: str


class RowIssue(BaseModel):
    row_number: int
    severity: Literal["ERROR", "CONFLICT"] = "ERROR"
    messages: List[str] = Field(default_factory=list)


class ImportParseResult(BaseModel):
    import_type: Literal["TASK_ONLY", "PRE_SCHEDULED"]
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"]
    status: Literal["SUCCESS", "PARTIAL_CONFLICT", "ROLLED_BACK"]
    total_rows: int
    valid_rows: int
    conflict_rows: int
    issues: List[RowIssue] = Field(default_factory=list)
    parsed_tasks: List[ParsedTaskRow] = Field(default_factory=list)
    parsed_pre_schedules: List[ParsedPreScheduleRow] = Field(default_factory=list)
