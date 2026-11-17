"""Allow verification officer users.

Revision ID: c4b73a19d620
Revises: 2f14c6a90b31
"""
from alembic import op


revision = "c4b73a19d620"
down_revision = "2f14c6a90b31"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("users_role", "users", type_="check")
    op.create_check_constraint(
        "users_role",
        "users",
        "role IN ('CITIZEN','REGISTRAR','VERIFICATION_OFFICER','ADMIN')",
    )


def downgrade():
    op.drop_constraint("users_role", "users", type_="check")
    op.create_check_constraint(
        "users_role",
        "users",
        "role IN ('CITIZEN','REGISTRAR','ADMIN')",
    )
