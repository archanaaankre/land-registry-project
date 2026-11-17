"""Add user account activation state.

Revision ID: d9f36b2a1c84
Revises: c4b73a19d620
"""
from alembic import op
import sqlalchemy as sa


revision = "d9f36b2a1c84"
down_revision = "c4b73a19d620"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade():
    op.drop_column("users", "is_active")
