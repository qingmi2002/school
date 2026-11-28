"""V2.0 add cohort lifecycle (study_years, graduation_year, cohort_status) and org_node_manager table.

Revision ID: 0008_v2_0_org_cohort
Revises: 0007_v1_6_hours_opt
Create Date: 2026-11-28
"""
from alembic import op
import sqlalchemy as sa
from app.db.session import Base
import app.models  # noqa: F401

revision = "0008_v2_0_org_cohort"
down_revision = "0007_v1_6_hours_opt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    insp = sa.inspect(bind)

    if insp.has_table("student_cohort"):
        cols = {c["name"] for c in insp.get_columns("student_cohort")}
        if "study_years" not in cols:
            op.add_column("student_cohort", sa.Column("study_years", sa.SmallInteger(), nullable=False, server_default="4"))
        if "graduation_year" not in cols:
            op.add_column("student_cohort", sa.Column("graduation_year", sa.SmallInteger(), nullable=True))
        if "cohort_status" not in cols:
            op.add_column("student_cohort", sa.Column("cohort_status", sa.String(length=16), nullable=False, server_default="ACTIVE"))

    if not insp.has_table("org_node_manager"):
        op.create_table(
            "org_node_manager",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("org_node_id", sa.Integer(), sa.ForeignKey("org_node.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title_name", sa.String(length=60), nullable=False),
            sa.Column("permission_level", sa.String(length=24), nullable=False, server_default="SCHEDULER"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    pass
