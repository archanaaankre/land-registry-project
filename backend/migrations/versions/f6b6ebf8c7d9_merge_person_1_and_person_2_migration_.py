"""merge Person 1 and Person 2 migration branches

Revision ID: f6b6ebf8c7d9
Revises: d9f36b2a1c84, e9c41a7b6d20
Create Date: 2026-11-15 17:18:40.927436

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6b6ebf8c7d9'
down_revision = ('d9f36b2a1c84', 'e9c41a7b6d20')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
