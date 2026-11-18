"""Add user account activation state (defensive).

Revision ID: d9f36b2a1c84
Revises: c4b73a19d620

A database upgraded along Person 2's branch may already have ``is_active``
without a server default. This revision adds the column with a server default
when missing, and repairs the default on PostgreSQL when the column exists.
"""
from alembic import op
import sqlalchemy as sa


revision = "d9f36b2a1c84"
down_revision = "c4b73a19d620"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = {column["name"]: column for column in insp.get_columns("users")}

    if "is_active" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        return

    # Column already present (Person 2 branch). Ensure future raw inserts get
    # a valid value. SQLite cannot ALTER a column default in place; the ORM
    # always supplies the value there, so only PostgreSQL needs the repair.
    if columns["is_active"].get("default") is None and bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT true"))


def downgrade():
    insp = sa.inspect(op.get_bind())
    if any(column["name"] == "is_active" for column in insp.get_columns("users")):
        op.drop_column("users", "is_active")
