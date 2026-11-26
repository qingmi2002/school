"""initial 16 core tables for multi-level flexible scheduling

Revision ID: 0001_initial_16_tables
Revises:
Create Date: 2026-11-26 08:35:00
"""
from alembic import op
from app.db.session import Base
import app.models  # noqa: F401

revision = "0001_initial_16_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
