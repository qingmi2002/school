"""v1.2 add system_config, schedule_policy_rule, classroom usage_mode, and semester dates

Revision ID: 0003_v1_2_config_rules_and_rooms
Revises: 0002_add_student_role_and_cohort
Create Date: 2026-11-26 15:10:00
"""
from alembic import op
import sqlalchemy as sa
from app.db.session import Base
import app.models  # noqa: F401

revision = "0003_v1_2_config_rules_and_rooms"
down_revision = "0002_add_student_role_and_cohort"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. 为老库平滑补充 semester.start_date / end_date
    sem_cols = {c["name"] for c in insp.get_columns("semester")}
    if "start_date" not in sem_cols:
        op.add_column("semester", sa.Column("start_date", sa.String(16), nullable=True))
    if "end_date" not in sem_cols:
        op.add_column("semester", sa.Column("end_date", sa.String(16), nullable=True))

    # 2. 为老库平滑补充 classroom.usage_mode (FIXED/FLOATING) 与 fixed_cohort_id
    room_cols = {c["name"] for c in insp.get_columns("classroom")}
    if "usage_mode" not in room_cols:
        op.add_column("classroom", sa.Column("usage_mode", sa.String(16), nullable=False, server_default="FLOATING"))
    if "fixed_cohort_id" not in room_cols:
        op.add_column("classroom", sa.Column("fixed_cohort_id", sa.Integer(), nullable=True))

    # 3. 创建新增的 system_config 与 schedule_policy_rule 表（幂等）
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass
