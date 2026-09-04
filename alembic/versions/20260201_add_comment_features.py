"""Add comment analysis features (JSON blob + timestamp)

Revision ID: 20260201_comments
Revises: 20260201_idx
Create Date: 2026-02-01 12:00:00.000000

Phase 4a implementation: Store comment-based spam detection metrics
in a JSON blob instead of 18 individual columns.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260201_comments'
down_revision = '20260201_idx'
branch_labels = None
depends_on = None


def upgrade():
    # Add comment analysis columns to user_spam_features table
    # Using JSON blob to store all metrics (matching feature_data pattern)
    op.add_column('user_spam_features', sa.Column('comment_features', sa.JSON(), nullable=True))
    op.add_column('user_spam_features', sa.Column('comment_analysis_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('user_spam_features', 'comment_analysis_at')
    op.drop_column('user_spam_features', 'comment_features')