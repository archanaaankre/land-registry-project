"""Merge Person 1 and Person 2 integration heads.

Revision ID: c9d0e1f2a3b4
Revises: b7e5c4d2a910, a7b8c9d0e1f2

Both branches are now part of a single history. No schema operation is needed
here: each branch's schema changes are applied by its own (defensive)
revisions, and f4a2b9c1d6e3 is an explicit no-op.
"""
from alembic import op  # noqa: F401


revision = "c9d0e1f2a3b4"
down_revision = ("b7e5c4d2a910", "a7b8c9d0e1f2")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
