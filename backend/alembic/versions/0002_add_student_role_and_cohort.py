"""add multi-tier scheduler roles, student role, and cohort_id on sys_user

Revision ID: 0002_add_student_role_and_cohort
Revises: 0001_initial_16_tables
Create Date: 2026-11-26 14:15:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_student_role_and_cohort"
down_revision = "0001_initial_16_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("sys_user")}
    if "cohort_id" not in cols:
        op.add_column("sys_user", sa.Column("cohort_id", sa.Integer(), nullable=True))
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE sys_user DROP CONSTRAINT IF EXISTS ck_sys_user_role;")
        op.execute(
            "ALTER TABLE sys_user ADD CONSTRAINT ck_sys_user_role "
            "CHECK (role_code IN ('SUPER_ADMIN', 'COLLEGE_SCHEDULER', 'DEPT_SCHEDULER', 'MAJOR_SCHEDULER', 'LAB_ADMIN', 'TEACHER', 'STUDENT'));"
        )


def downgrade() -> None:
    pass
