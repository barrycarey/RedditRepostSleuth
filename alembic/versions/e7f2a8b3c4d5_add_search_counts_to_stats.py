"""add search counts to stats

Revision ID: e7f2a8b3c4d5
Revises: 01cdf2a1a340
Create Date: 2026-01-21 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e7f2a8b3c4d5'
down_revision = '01cdf2a1a340'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stat_daily_count', sa.Column('image_searches_24h', sa.Integer(), nullable=True))
    op.add_column('stat_daily_count', sa.Column('link_searches_24h', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('stat_daily_count', 'link_searches_24h')
    op.drop_column('stat_daily_count', 'image_searches_24h')
