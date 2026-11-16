"""Add is_active to users and VERIFICATION_OFFICER role.

Revision ID: f4a2b9c1d6e3
Revises: e9c41a7b6d20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f4a2b9c1d6e3"
down_revision = "e9c41a7b6d20"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), default=True, nullable=False)
        )
        batch_op.drop_constraint("users_role", type_="check")
        batch_op.create_check_constraint(
            "role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')",
            name="users_role",
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("users_role", type_="check")
        batch_op.create_check_constraint(
            "role IN ('CITIZEN','REGISTRAR','ADMIN')", name="users_role"
        )
        batch_op.drop_column("is_active")
