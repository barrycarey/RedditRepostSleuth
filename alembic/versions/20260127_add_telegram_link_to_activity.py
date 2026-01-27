"""Add has_telegram_link to author_activity_tracking

Revision ID: 20260127_telegram
Revises: 20260127_modvote
Create Date: 2026-01-27 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260127_telegram'
down_revision = '20260127_modvote'
branch_labels = None
depends_on = None


def upgrade():
    # Add has_telegram_link column to author_activity_tracking table
    op.add_column(
        'author_activity_tracking',
        sa.Column('has_telegram_link', sa.Boolean(), nullable=True, server_default='0')
    )


def downgrade():
    op.drop_column('author_activity_tracking', 'has_telegram_link')
