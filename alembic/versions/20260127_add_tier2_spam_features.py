"""Add Tier 2 spam feature columns

Revision ID: 20260127_tier2
Revises: 20260126_spam
Create Date: 2026-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260127_tier2'
down_revision = '20260126_spam'
branch_labels = None
depends_on = None


def upgrade():
    # Add Tier 2 columns to user_spam_features table
    # These columns store data fetched from Reddit API

    # Account info from Reddit API (single call)
    op.add_column('user_spam_features', sa.Column('account_age_days', sa.Integer(), nullable=True))
    op.add_column('user_spam_features', sa.Column('total_karma', sa.Integer(), nullable=True))
    op.add_column('user_spam_features', sa.Column('post_karma', sa.Integer(), nullable=True))
    op.add_column('user_spam_features', sa.Column('comment_karma', sa.Integer(), nullable=True))
    op.add_column('user_spam_features', sa.Column('karma_per_day', sa.Float(), nullable=True))
    op.add_column('user_spam_features', sa.Column('has_verified_email', sa.Boolean(), nullable=True))
    op.add_column('user_spam_features', sa.Column('is_gold', sa.Boolean(), nullable=True))
    op.add_column('user_spam_features', sa.Column('has_custom_avatar', sa.Boolean(), nullable=True))
    op.add_column('user_spam_features', sa.Column('account_suspended', sa.Boolean(), nullable=True, server_default='0'))

    # Profile/comment scanning results (adult + telegram links)
    op.add_column('user_spam_features', sa.Column('has_adult_profile_links', sa.Boolean(), nullable=True))
    op.add_column('user_spam_features', sa.Column('has_telegram_links', sa.Boolean(), nullable=True))
    op.add_column('user_spam_features', sa.Column('profile_link_sources', sa.JSON(), nullable=True))

    # Tier 2 enrichment metadata
    op.add_column('user_spam_features', sa.Column('tier2_enriched_at', sa.DateTime(), nullable=True))
    op.add_column('user_spam_features', sa.Column('tier2_enrichment_failed', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('user_spam_features', sa.Column('tier2_failure_reason', sa.String(length=200), nullable=True))

    # Create index for finding users needing Tier 2 enrichment
    op.create_index('idx_tier2_enriched_at', 'user_spam_features', ['tier2_enriched_at'], unique=False)
    op.create_index('idx_account_suspended', 'user_spam_features', ['account_suspended'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index('idx_account_suspended', table_name='user_spam_features')
    op.drop_index('idx_tier2_enriched_at', table_name='user_spam_features')

    # Drop Tier 2 columns
    op.drop_column('user_spam_features', 'tier2_failure_reason')
    op.drop_column('user_spam_features', 'tier2_enrichment_failed')
    op.drop_column('user_spam_features', 'tier2_enriched_at')
    op.drop_column('user_spam_features', 'profile_link_sources')
    op.drop_column('user_spam_features', 'has_telegram_links')
    op.drop_column('user_spam_features', 'has_adult_profile_links')
    op.drop_column('user_spam_features', 'account_suspended')
    op.drop_column('user_spam_features', 'has_custom_avatar')
    op.drop_column('user_spam_features', 'is_gold')
    op.drop_column('user_spam_features', 'has_verified_email')
    op.drop_column('user_spam_features', 'karma_per_day')
    op.drop_column('user_spam_features', 'comment_karma')
    op.drop_column('user_spam_features', 'post_karma')
    op.drop_column('user_spam_features', 'total_karma')
    op.drop_column('user_spam_features', 'account_age_days')
