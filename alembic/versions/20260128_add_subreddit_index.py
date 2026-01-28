"""Add subreddit index for author_activity_tracking

Adds idx_subreddit index to enable efficient subreddit-first queries
for filtering voting queue by moderator's subreddits.

Revision ID: 20260128_subidx
Revises: 20260127_post_scan
Create Date: 2026-01-28 10:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '20260128_subidx'
down_revision = '20260127_post_scan'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('idx_subreddit', 'author_activity_tracking', ['subreddit'])


def downgrade():
    op.drop_index('idx_subreddit', table_name='author_activity_tracking')
