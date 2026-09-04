"""Add indexes for repost table optimization

Adds indexes to optimize the update_top_reposts and update_top_reposters
scheduled tasks that were causing MySQL connection losses due to full table scans.

- idx_repost_of_id_posttype: For GROUP BY repost_of_id queries
- idx_repost_author_stats: Covering index for author grouping queries

IMPORTANT: Run this migration during off-peak hours. With 100M+ rows,
index creation may take significant time.

Revision ID: 20260201_idx
Revises: 20260129_easy_karma
Create Date: 2026-02-01

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '20260201_idx'
down_revision = '20260129_easy_karma'
branch_labels = None
depends_on = None


def upgrade():
    # Index for update_top_reposts GROUP BY repost_of_id
    # This allows efficient grouping by (post_type_id, repost_of_id)
    op.create_index('idx_repost_of_id_posttype', 'repost', ['post_type_id', 'repost_of_id'])

    # Covering index for update_top_reposters
    # Includes author as the last column for efficient GROUP BY author
    op.create_index('idx_repost_author_stats', 'repost', ['post_type_id', 'detected_at', 'author'])


def downgrade():
    op.drop_index('idx_repost_of_id_posttype', table_name='repost')
    op.drop_index('idx_repost_author_stats', table_name='repost')
