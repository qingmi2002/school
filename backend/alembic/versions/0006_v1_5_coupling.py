"""V1.5 course library, combined-class coupling, teacher priority and week_mask on teacher_unavailable.

Revision ID: 0006_v1_5_coupling
Revises: 0005_v1_4_week_plan
Create Date: 2026-11-27
"""
from alembic import op
import sqlalchemy as sa
from app.db.session import Base
import app.models  # noqa: F401

revision = "0006_v1_5_coupling"
down_revision = "0005_v1_4_week_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    insp = sa.inspect(bind)

    if not insp.has_table("course"):
        op.create_table(
            "course",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_org_id", sa.Integer(), sa.ForeignKey("org_node.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("course_code", sa.String(length=40), nullable=False, unique=True),
            sa.Column("course_name", sa.String(length=120), nullable=False),
            sa.Column("course_category", sa.String(length=20), nullable=False, server_default="THEORY"),
            sa.Column("required_room_type", sa.String(length=24), nullable=False, server_default="NORMAL"),
            sa.Column("default_weekly_sessions", sa.SmallInteger(), nullable=False, server_default="2"),
            sa.Column("allow_combined", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    sys_user_cols = {c["name"] for c in insp.get_columns("sys_user")}
    if "teacher_priority" not in sys_user_cols:
        op.add_column("sys_user", sa.Column("teacher_priority", sa.SmallInteger(), nullable=False, server_default="1"))

    tu_cols = {c["name"] for c in insp.get_columns("teacher_unavailable")}
    if "week_mask" not in tu_cols:
        op.add_column("teacher_unavailable", sa.Column("week_mask", sa.Integer(), nullable=True))

    tt_cols = {c["name"] for c in insp.get_columns("teaching_task")}
    if "course_id" not in tt_cols:
        op.add_column(
            "teaching_task",
            sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id", ondelete="SET NULL"), nullable=True),
        )
    if "required_room_type" not in tt_cols:
        op.add_column("teaching_task", sa.Column("required_room_type", sa.String(length=24), nullable=True))

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE sys_user DROP CONSTRAINT IF EXISTS ck_sys_user_role")
        op.execute(
            "ALTER TABLE sys_user ADD CONSTRAINT ck_sys_user_role "
            "CHECK (role_code IN ('SUPER_ADMIN', 'COLLEGE_SCHEDULER', 'DEPT_SCHEDULER', 'MAJOR_SCHEDULER', 'LAB_ADMIN', 'TEACHING_LEAD', 'TEACHER', 'STUDENT'))"
        )
        op.execute("ALTER TABLE classroom DROP CONSTRAINT IF EXISTS ck_classroom_type")
        op.execute(
            "ALTER TABLE classroom ADD CONSTRAINT ck_classroom_type "
            "CHECK (room_type IN ('NORMAL', 'COMPUTER_LAB', 'NETWORK_LAB', 'TRAINING_ROOM', 'LECTURE_HALL', 'SPORTS'))"
        )


def downgrade() -> None:
    pass
