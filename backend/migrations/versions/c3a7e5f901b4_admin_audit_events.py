"""Create admin_audit_events table for admin action audit trail.

Revision ID: c3a7e5f901b4
Revises: a7b8c9d0e1f2
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c3a7e5f901b4"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_audit_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("target_user_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_role", sa.String(length=32), nullable=True),
        sa.Column("to_role", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('USER_CREATED','USER_ROLE_CHANGED','USER_ACTIVATED','USER_DEACTIVATED')",
            name="admin_audit_events_event_type",
        ),
        sa.CheckConstraint(
            "actor_role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')",
            name="admin_audit_events_actor_role",
        ),
        sa.CheckConstraint(
            "from_role IS NULL OR from_role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')",
            name="admin_audit_events_from_role",
        ),
        sa.CheckConstraint(
            "to_role IS NULL OR to_role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')",
            name="admin_audit_events_to_role",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_admin_audit_events_actor_id",
        "admin_audit_events",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_events_target_user_id",
        "admin_audit_events",
        ["target_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_events_created_at",
        "admin_audit_events",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_admin_audit_events_created_at", table_name="admin_audit_events"
    )
    op.drop_index(
        "ix_admin_audit_events_target_user_id", table_name="admin_audit_events"
    )
    op.drop_index(
        "ix_admin_audit_events_actor_id", table_name="admin_audit_events"
    )
    op.drop_table("admin_audit_events")
