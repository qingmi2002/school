"""
核心数据模型（16 张表）
V1.1 升级：支持校级/院级/系级/专业级四级排课管理员、机房管理员、任课教师与学生（关联行政班 cohort_id）。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class NodeType(Base):
    __tablename__ = "node_type"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    default_flags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)


class OrgNode(Base):
    __tablename__ = "org_node"
    __table_args__ = (
        Index("ix_org_node_tree_path", "tree_path"),
        Index("ix_org_node_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=True
    )
    node_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    node_name: Mapped[str] = mapped_column(String(120), nullable=False)
    node_type_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("node_type.code", ondelete="RESTRICT"), nullable=False
    )
    tree_path: Mapped[str] = mapped_column(String(512), nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)

    is_scheduling_unit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public_provider: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_student_cohort: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_room_pool: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_campus_boundary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_summary_node: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_custom_timeslot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    parent: Mapped[Optional["OrgNode"]] = relationship("OrgNode", remote_side=[id])


class OrgResourceGrant(Base):
    __tablename__ = "org_resource_grant"
    __table_args__ = (
        UniqueConstraint(
            "granter_org_id",
            "grantee_org_id",
            "resource_type",
            "semester_id",
            name="uq_org_resource_grant_scope",
        ),
        CheckConstraint("granter_org_id <> grantee_org_id", name="ck_grant_not_self"),
        CheckConstraint(
            "resource_type IN ('ROOM_POOL', 'TEACHER', 'PUBLIC_COURSE')",
            name="ck_grant_resource_type",
        ),
        CheckConstraint(
            "grant_mode IN ('FULL', 'IDLE_ONLY', 'APPROVAL_REQUIRED')",
            name="ck_grant_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    granter_org_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("org_node.id", ondelete="CASCADE"), nullable=False
    )
    grantee_org_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("org_node.id", ondelete="CASCADE"), nullable=False
    )
    semester_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("semester.id", ondelete="CASCADE"), nullable=True
    )
    resource_type: Mapped[str] = mapped_column(String(24), nullable=False)
    grant_mode: Mapped[str] = mapped_column(String(24), default="IDLE_ONLY", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SysUser(Base):
    """系统用户与分级 RBAC 角色表（支持校级/院级/系级/专业级排课员、机房管理员、教师、学生）"""

    __tablename__ = "sys_user"
    __table_args__ = (
        CheckConstraint(
            "role_code IN ('SUPER_ADMIN', 'COLLEGE_SCHEDULER', 'DEPT_SCHEDULER', 'MAJOR_SCHEDULER', 'LAB_ADMIN', 'TEACHER', 'STUDENT')",
            name="ck_sys_user_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    real_name: Mapped[str] = mapped_column(String(60), nullable=False)
    org_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False
    )
    cohort_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("student_cohort.id", ondelete="SET NULL"), nullable=True
    )
    role_code: Mapped[str] = mapped_column(String(30), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ExcelImportBatch(Base):
    __tablename__ = "excel_import_batch"
    __table_args__ = (
        CheckConstraint("import_type IN ('TASK_ONLY', 'PRE_SCHEDULED')", name="ck_excel_import_type"),
        CheckConstraint("status IN ('SUCCESS', 'PARTIAL_CONFLICT', 'ROLLED_BACK')", name="ck_excel_import_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    semester_id: Mapped[int] = mapped_column(Integer, ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False)
    org_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False)
    operator_id: Mapped[int] = mapped_column(Integer, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False)
    import_type: Mapped[str] = mapped_column(String(30), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conflict_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    conflict_report: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Semester(Base):
    __tablename__ = "semester"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    total_weeks: Mapped[int] = mapped_column(SmallInteger, default=18, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Timeslot(Base):
    __tablename__ = "timeslot"
    __table_args__ = (
        UniqueConstraint("org_node_id", "day_of_week", "period_index", name="uq_timeslot_node_slot"),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_timeslot_day"),
        CheckConstraint("period_index >= 1", name="ck_timeslot_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_node_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("org_node.id", ondelete="CASCADE"), nullable=True
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period_name: Mapped[str] = mapped_column(String(40), nullable=False)
    start_time: Mapped[Optional[str]] = mapped_column(String(8))
    end_time: Mapped[Optional[str]] = mapped_column(String(8))
    is_evening: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StudentCohort(Base):
    __tablename__ = "student_cohort"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cohort_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    cohort_name: Mapped[str] = mapped_column(String(100), nullable=False)
    org_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False)
    grade_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    student_count: Mapped[int] = mapped_column(Integer, default=30, nullable=False)


class Classroom(Base):
    __tablename__ = "classroom"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_classroom_capacity"),
        CheckConstraint("room_type IN ('NORMAL', 'COMPUTER_LAB', 'NETWORK_LAB', 'TRAINING_ROOM', 'SPORTS')", name="ck_classroom_type"),
        CheckConstraint("sharing_policy IN ('EXCLUSIVE', 'IDLE_BORROW', 'PUBLIC_POOL')", name="ck_classroom_sharing_policy"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    building: Mapped[str] = mapped_column(String(60), nullable=False)
    owner_org_id: Mapped[int] = mapped_column(Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    room_type: Mapped[str] = mapped_column(String(24), nullable=False)
    env_tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    sharing_policy: Mapped[str] = mapped_column(String(24), default="IDLE_BORROW", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TeachingTask(Base):
    __tablename__ = "teaching_task"
    __table_args__ = (
        CheckConstraint("course_category IN ('THEORY', 'LAB', 'MIXED')", name="ck_task_course_category"),
        CheckConstraint("course_level IN ('PUBLIC', 'COLLEGE', 'DEPT')", name="ck_task_course_level"),
        CheckConstraint("week_type IN (0, 1, 2)", name="ck_task_week_type"),
        CheckConstraint("weekly_sessions > 0", name="ck_task_weekly_sessions"),
        CheckConstraint("total_students > 0", name="ck_task_total_students"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    semester_id: Mapped[int] = mapped_column(Integer, ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False)
    org_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False)
    course_code: Mapped[str] = mapped_column(String(40), nullable=False)
    course_name: Mapped[str] = mapped_column(String(120), nullable=False)
    course_category: Mapped[str] = mapped_column(String(20), nullable=False)
    course_level: Mapped[str] = mapped_column(String(20), default="DEPT", nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False)
    cohort_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    weekly_sessions: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    week_type: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    start_week: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    end_week: Mapped[int] = mapped_column(SmallInteger, default=18, nullable=False)
    total_students: Mapped[int] = mapped_column(Integer, nullable=False)
    required_env_tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PublicCourseLock(Base):
    __tablename__ = "public_course_lock"
    __table_args__ = (CheckConstraint("week_type IN (0, 1, 2)", name="ck_lock_week_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    semester_id: Mapped[int] = mapped_column(Integer, ForeignKey("semester.id", ondelete="CASCADE"), nullable=False)
    lock_scope_org_id: Mapped[int] = mapped_column(Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False)
    timeslot_id: Mapped[int] = mapped_column(Integer, ForeignKey("timeslot.id", ondelete="RESTRICT"), nullable=False)
    week_type: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    cohort_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("student_cohort.id", ondelete="CASCADE"), nullable=True)
    classroom_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("classroom.id", ondelete="CASCADE"), nullable=True)
    teacher_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=True)
    course_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_readonly: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TeacherUnavailable(Base):
    __tablename__ = "teacher_unavailable"
    __table_args__ = (
        UniqueConstraint("semester_id", "teacher_id", "timeslot_id", name="uq_teacher_unavail_slot"),
        CheckConstraint("constraint_level IN ('HARD', 'SOFT')", name="ck_teacher_unavail_level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    semester_id: Mapped[int] = mapped_column(Integer, ForeignKey("semester.id", ondelete="CASCADE"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False)
    timeslot_id: Mapped[int] = mapped_column(Integer, ForeignKey("timeslot.id", ondelete="CASCADE"), nullable=False)
    constraint_level: Mapped[str] = mapped_column(String(10), default="HARD", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(120))


class RoomCourseRule(Base):
    __tablename__ = "room_course_rule"
    __table_args__ = (CheckConstraint("rule_type IN ('ALLOW', 'DENY')", name="ck_room_rule_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    classroom_id: Mapped[int] = mapped_column(Integer, ForeignKey("classroom.id", ondelete="CASCADE"), nullable=False)
    course_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    course_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(10), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=10, nullable=False)


class SchedulePlan(Base):
    __tablename__ = "schedule_plan"
    __table_args__ = (CheckConstraint("run_mode IN ('SINGLE_DEPT', 'SCHOOL_WIDE')", name="ck_plan_run_mode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    semester_id: Mapped[int] = mapped_column(Integer, ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False)
    org_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(120), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(40), nullable=False)
    run_mode: Mapped[str] = mapped_column(String(20), default="SINGLE_DEPT", nullable=False)
    fitness_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    cloud_archive_path: Mapped[Optional[str]] = mapped_column(String(500))
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ScheduleDetail(Base):
    __tablename__ = "schedule_detail"
    __table_args__ = (
        UniqueConstraint("plan_id", "timeslot_id", "classroom_id", "week_type", name="uq_detail_room_slot_week"),
        CheckConstraint("week_type IN (0, 1, 2)", name="ck_detail_week_type"),
        Index("ix_schedule_detail_plan_slot", "plan_id", "timeslot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_plan.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("teaching_task.id", ondelete="RESTRICT"), nullable=False)
    timeslot_id: Mapped[int] = mapped_column(Integer, ForeignKey("timeslot.id", ondelete="RESTRICT"), nullable=False)
    classroom_id: Mapped[int] = mapped_column(Integer, ForeignKey("classroom.id", ondelete="RESTRICT"), nullable=False)
    week_type: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    is_manual_adjusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ScheduleChangeAudit(Base):
    __tablename__ = "schedule_change_audit"
    __table_args__ = (
        CheckConstraint("audit_type IN ('CHANGE_REQUEST', 'ARCHIVE_SYNC')", name="ck_audit_type"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'SYNCED', 'FAILED')", name="ck_audit_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_plan.id", ondelete="CASCADE"), nullable=False)
    operator_id: Mapped[int] = mapped_column(Integer, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False)
    audit_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
