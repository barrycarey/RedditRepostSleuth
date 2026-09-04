"""Optimize spam scoring queries with author index

Adds standalone author index to author_activity_tracking table to enable
efficient GROUP BY operations in spam scoring queries.

This index supports the LEFT JOIN exclusion pattern used by:
- get_unscored_users()
- get_top_reposters()
- get_high_activity_users()

Revision ID: 20260128_authidx
Revises: 20260128_subidx
Create Date: 2026-01-28 14:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '20260128_authidx'
down_revision = '20260128_subidx'
branch_labels = None
depends_on = None


def upgrade():
    # Standalone author index for GROUP BY operations
    op.create_index('idx_author', 'author_activity_tracking', ['author'], unique=False)


def downgrade():
    op.drop_index('idx_author', table_name='author_activity_tracking')
