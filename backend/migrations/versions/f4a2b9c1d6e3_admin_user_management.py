"""Admin user management schema revision (retired as a no-op).

Revision ID: f4a2b9c1d6e3
Revises: e9c41a7b6d20

This revision is retained so databases that already recorded it remain on a
valid Alembic history. Its original operations (adding users.is_active and
changing the role CHECK constraint) are now performed -- defensively and once
only -- by revisions c4b73a19d620 and d9f36b2a1c84 on the Person 1 branch.

Re-running those operations here would either fail (duplicate column) or
create a duplicate/malformed constraint, so this revision intentionally does
nothing. Changing this file does NOT repair an already-applied database; the
defensive code in the two revisions above is what handles that case when a
database upgrades from this head to the merged head.
"""
from alembic import op  # noqa: F401  (kept for Alembic migration conventions)


revision = "f4a2b9c1d6e3"
down_revision = "e9c41a7b6d20"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
