"""Add moderator spam voting tables (Phase 5.5)

Revision ID: 20260127_modvote
Revises: 20260127_tier2
Create Date: 2026-01-27 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260127_modvote'
down_revision = '20260127_tier2'
branch_labels = None
depends_on = None


def upgrade():
    # Create moderator_spam_vote table
    op.create_table(
        'moderator_spam_vote',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target_username', sa.String(length=25), nullable=False),
        sa.Column('moderator_username', sa.String(length=25), nullable=False),
        sa.Column('subreddit', sa.String(length=25), nullable=False),
        sa.Column('subreddit_subscribers', sa.Integer(), nullable=False),
        sa.Column('vote', sa.Integer(), nullable=False),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('voted_at', sa.DateTime(), nullable=True),
        sa.Column('spam_score_at_vote', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for moderator_spam_vote
    op.create_index('idx_mod_vote_target', 'moderator_spam_vote', ['target_username'], unique=False)
    op.create_index('idx_mod_vote_moderator', 'moderator_spam_vote', ['moderator_username'], unique=False)
    op.create_index('idx_mod_vote_voted_at', 'moderator_spam_vote', ['voted_at'], unique=False)

    # Create unique constraint for one vote per moderator per user
    op.create_unique_constraint('uq_target_moderator', 'moderator_spam_vote', ['target_username', 'moderator_username'])

    # Add moderator voting aggregate columns to user_spam_features
    op.add_column('user_spam_features', sa.Column('mod_vote_total', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('user_spam_features', sa.Column('mod_vote_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('user_spam_features', sa.Column('mod_vote_weighted', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('user_spam_features', sa.Column('mod_vote_updated_at', sa.DateTime(), nullable=True))
    op.add_column('user_spam_features', sa.Column('mod_vote_consensus', sa.String(length=20), nullable=True))


def downgrade():
    # Drop mod_vote columns from user_spam_features
    op.drop_column('user_spam_features', 'mod_vote_consensus')
    op.drop_column('user_spam_features', 'mod_vote_updated_at')
    op.drop_column('user_spam_features', 'mod_vote_weighted')
    op.drop_column('user_spam_features', 'mod_vote_count')
    op.drop_column('user_spam_features', 'mod_vote_total')

    # Drop unique constraint
    op.drop_constraint('uq_target_moderator', 'moderator_spam_vote', type_='unique')

    # Drop indexes
    op.drop_index('idx_mod_vote_voted_at', table_name='moderator_spam_vote')
    op.drop_index('idx_mod_vote_moderator', table_name='moderator_spam_vote')
    op.drop_index('idx_mod_vote_target', table_name='moderator_spam_vote')

    # Drop table
    op.drop_table('moderator_spam_vote')
