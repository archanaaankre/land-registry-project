"""Create the admin_audit_events table for the admin user-management audit trail.

Revision ID: f2d8e5a1b7c3
Revises: d8e4b9a2f6c7

Defensive: if the table already exists (e.g. a partially upgraded database),
only the missing indexes are created; the table is left untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "f2d8e5a1b7c3"
down_revision = "d8e4b9a2f6c7"
branch_labels = None
depends_on = None

_TABLE = "admin_audit_events"


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        op.create_table(
            _TABLE,
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
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("event_id"),
        )
    insp = sa.inspect(op.get_bind())
    existing = {index["name"] for index in insp.get_indexes(_TABLE)}
    for name, columns in (
        ("ix_admin_audit_events_actor_id", ["actor_id"]),
        ("ix_admin_audit_events_target_user_id", ["target_user_id"]),
        ("ix_admin_audit_events_created_at", ["created_at"]),
    ):
        if name not in existing:
            op.create_index(name, _TABLE, columns)


def downgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {index["name"] for index in insp.get_indexes(_TABLE)}
    for name in (
        "ix_admin_audit_events_created_at",
        "ix_admin_audit_events_target_user_id",
        "ix_admin_audit_events_actor_id",
    ):
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
