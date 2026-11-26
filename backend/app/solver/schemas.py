"""T1.4 求解器纯领域 DTO（与 ORM 解耦，支持单元测试与 Celery 序列化）。"""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SolverTimeslot(BaseModel):
    id: int
    day_of_week: int  # 1..7
    period_index: int  # 1..5
    period_name: str = ""
    is_evening: bool = False


class SolverRoom(BaseModel):
    id: int
    room_code: str
    owner_org_id: int
    campus_boundary_id: Optional[int] = None
    capacity: int
    room_type: str = "NORMAL"  # NORMAL / COMPUTER_LAB / NETWORK_LAB / TRAINING_ROOM / SPORTS
    env_tags: List[str] = Field(default_factory=list)


class SolverTask(BaseModel):
    id: int
    org_node_id: int
    course_code: str
    course_name: str
    course_category: Literal["THEORY", "LAB", "MIXED"] = "THEORY"
    teacher_id: int
    cohort_ids: List[int] = Field(default_factory=list)
    weekly_sessions: int = 1
    week_type: int = 0  # 0=全周, 1=单周, 2=双周
    total_students: int = 30
    required_env_tags: List[str] = Field(default_factory=list)


class SolverPublicLock(BaseModel):
    timeslot_id: int
    week_type: int = 0  # 0=全周, 1=单周, 2=双周
    cohort_id: Optional[int] = None
    classroom_id: Optional[int] = None
    teacher_id: Optional[int] = None
    course_name: str = "公共课"


class SolverTeacherUnavailable(BaseModel):
    teacher_id: int
    timeslot_id: int
    constraint_level: Literal["HARD", "SOFT"] = "HARD"
    reason: Optional[str] = None


class SolverRoomRule(BaseModel):
    classroom_id: int
    course_code: Optional[str] = None
    course_category: Optional[str] = None
    rule_type: Literal["ALLOW", "DENY"]


class SolverInput(BaseModel):
    run_mode: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = "SINGLE_DEPT"
    timeslots: List[SolverTimeslot]
    rooms: List[SolverRoom]
    tasks: List[SolverTask]
    public_locks: List[SolverPublicLock] = Field(default_factory=list)
    teacher_unavailable: List[SolverTeacherUnavailable] = Field(default_factory=list)
    room_rules: List[SolverRoomRule] = Field(default_factory=list)
    time_limit_seconds: float = 10.0
    num_search_workers: int = 4


class ScheduledAssignment(BaseModel):
    task_id: int
    timeslot_id: int
    classroom_id: int
    week_type: int


class UnscheduledDiagnostic(BaseModel):
    task_id: int
    course_code: str
    course_name: str
    required_sessions: int
    scheduled_sessions: int
    reasons: List[str] = Field(default_factory=list)


class SolverResult(BaseModel):
    status: Literal["OPTIMAL", "FEASIBLE", "PARTIAL_RELAXED", "INFEASIBLE"]
    stage_used: int  # 1=严格零冲突求解, 2=松弛诊断求解
    solve_seconds: float
    fitness_score: float
    assignments: List[ScheduledAssignment] = Field(default_factory=list)
    unscheduled_diagnostics: List[UnscheduledDiagnostic] = Field(default_factory=list)
    stats: Dict[str, int] = Field(default_factory=dict)
