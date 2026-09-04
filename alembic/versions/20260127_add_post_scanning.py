"""Add post scanning column to user_spam_features

Revision ID: 20260127_post_scan
Revises: 20260127_telegram
Create Date: 2026-01-27 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260127_post_scan'
down_revision = '20260127_telegram'
branch_labels = None
depends_on = None


def upgrade():
    # Add column for promotional links found in user's posts
    # Adult and Telegram links in posts are merged into existing columns
    op.add_column('user_spam_features', sa.Column('has_promotional_post_links', sa.Boolean(), nullable=True))

    # Create index for querying users with promotional post links
    op.create_index('idx_has_promotional_post_links', 'user_spam_features', ['has_promotional_post_links'], unique=False)


def downgrade():
    op.drop_index('idx_has_promotional_post_links', table_name='user_spam_features')
    op.drop_column('user_spam_features', 'has_promotional_post_links')
