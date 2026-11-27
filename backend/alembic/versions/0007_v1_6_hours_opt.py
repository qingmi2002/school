"""V1.6 add course default_total_hours, teaching_task total_hours and prefer_consecutive.

Revision ID: 0007_v1_6_hours_opt
Revises: 0006_v1_5_coupling
Create Date: 2026-11-27
"""
from alembic import op
import sqlalchemy as sa
from app.db.session import Base
import app.models  # noqa: F401

revision = "0007_v1_6_hours_opt"
down_revision = "0006_v1_5_coupling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    insp = sa.inspect(bind)

    if insp.has_table("course"):
        c_cols = {c["name"] for c in insp.get_columns("course")}
        if "default_total_hours" not in c_cols:
            op.add_column("course", sa.Column("default_total_hours", sa.SmallInteger(), nullable=False, server_default="32"))

    if insp.has_table("teaching_task"):
        t_cols = {c["name"] for c in insp.get_columns("teaching_task")}
        if "total_hours" not in t_cols:
            op.add_column("teaching_task", sa.Column("total_hours", sa.SmallInteger(), nullable=True))
        if "prefer_consecutive" not in t_cols:
            op.add_column("teaching_task", sa.Column("prefer_consecutive", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    pass
