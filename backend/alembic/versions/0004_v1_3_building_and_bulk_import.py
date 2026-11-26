"""v1.3 add independent building table and classroom.building_id

Revision ID: 0004_v1_3_building_and_bulk_import
Revises: 0003_v1_2_config_rules_and_rooms
Create Date: 2026-11-26 15:35:00
"""
from alembic import op
import sqlalchemy as sa
from app.db.session import Base
import app.models  # noqa: F401

revision = "0004_v1_3_building_and_bulk_import"
down_revision = "0003_v1_2_config_rules_and_rooms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("classroom")}
    if "building_id" not in cols:
        op.add_column("classroom", sa.Column("building_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    pass
