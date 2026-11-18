"""Allow verification officer users (defensive).

Revision ID: c4b73a19d620
Revises: 2f14c6a90b31

Defensive upgrade: databases that already applied Person 2's
``f4a2b9c1d6e3`` may already carry an equivalent CHECK constraint, possibly
under a different name. Inspect the live schema and only add/replace what is
missing, so upgrading from either Person 1's head or Person 2's head works.
"""
from alembic import op
import sqlalchemy as sa


revision = "c4b73a19d620"
down_revision = "2f14c6a90b31"
branch_labels = None
depends_on = None

_ROLE_CHECK = "role IN ('CITIZEN','REGISTRAR','VERIFICATION_OFFICER','ADMIN')"
_OLD_ROLE_CHECK = "role IN ('CITIZEN','REGISTRAR','ADMIN')"


def _role_check_constraint(insp):
    for constraint in insp.get_check_constraints("users"):
        sqltext = (constraint.get("sqltext") or "").upper()
        if "ROLE" in sqltext:
            return constraint
    return None


def upgrade():
    insp = sa.inspect(op.get_bind())
    constraint = _role_check_constraint(insp)
    if constraint is not None:
        sqltext = (constraint.get("sqltext") or "").upper()
        if (
            "VERIFICATION_OFFICER" in sqltext
            and constraint.get("name") == "users_role"
        ):
            return  # already correct
        name = constraint.get("name")
        if name:
            op.drop_constraint(name, "users", type_="check")
    op.create_check_constraint("users_role", "users", _ROLE_CHECK)


def downgrade():
    insp = sa.inspect(op.get_bind())
    constraint = _role_check_constraint(insp)
    if constraint is not None and constraint.get("name"):
        op.drop_constraint(constraint["name"], "users", type_="check")
    op.create_check_constraint("users_role", "users", _OLD_ROLE_CHECK)
