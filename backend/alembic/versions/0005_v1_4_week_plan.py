"""v1.4 add cohort_week_plan table and week_mask bitmask columns

Revision ID: 0005_v1_4_week_plan
Revises: 0004_v1_3_building
Create Date: 2026-11-26 16:48:00
"""
from alembic import op
import sqlalchemy as sa
from app.db.session import Base
import app.models  # noqa: F401

revision = "0005_v1_4_week_plan"
down_revision = "0004_v1_3_building"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    insp = sa.inspect(bind)

    for tbl in ("teaching_task", "schedule_detail"):
        cols = {c["name"] for c in insp.get_columns(tbl)}
        if "week_mask" not in cols:
            op.add_column(tbl, sa.Column("week_mask", sa.Integer(), nullable=True))


def downgrade() -> None:
    pass
