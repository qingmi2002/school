"""V1.5 course library, combined-class coupling, teacher priority and week_mask on teacher_unavailable.

Revision ID: 0006_v1_5_coupling
Revises: 0005_v1_4_week_plan
Create Date: 2026-11-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_v1_5_coupling"
down_revision = "0005_v1_4_week_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.add_column("sys_user", sa.Column("teacher_priority", sa.SmallInteger(), nullable=False, server_default="1"))
    op.add_column("teacher_unavailable", sa.Column("week_mask", sa.Integer(), nullable=True))
    op.add_column(
        "teaching_task",
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("teaching_task", sa.Column("required_room_type", sa.String(length=24), nullable=True))


def downgrade() -> None:
    op.drop_column("teaching_task", "required_room_type")
    op.drop_column("teaching_task", "course_id")
    op.drop_column("teacher_unavailable", "week_mask")
    op.drop_column("sys_user", "teacher_priority")
    op.drop_table("course")
