"""add check_crossposts to monitored_sub

Revision ID: a1b2c3d4e5f6
Revises: e7f2a8b3c4d5
Create Date: 2026-01-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e7f2a8b3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('monitored_sub', sa.Column('check_crossposts', sa.Boolean(), nullable=True, server_default='0'))
    # Update existing rows to have explicit False value
    op.execute("UPDATE monitored_sub SET check_crossposts = 0 WHERE check_crossposts IS NULL")


def downgrade():
    op.drop_column('monitored_sub', 'check_crossposts')
