"""spam detection schema

Revision ID: 20260126_spam
Revises: a1b2c3d4e5f6
Create Date: 2026-01-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '20260126_spam'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Create author_activity_tracking table
    op.create_table('author_activity_tracking',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('post_id', sa.String(length=15), nullable=False),
        sa.Column('author', sa.String(length=25), nullable=False),
        sa.Column('subreddit', sa.String(length=25), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('post_type_id', mysql.TINYINT(), nullable=False),
        sa.Column('is_nsfw', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('has_adult_link', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('has_short_link', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('tracked_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id')
    )
    op.create_index('idx_author_created', 'author_activity_tracking', ['author', 'created_at'], unique=False)
    op.create_index('idx_author_subreddit', 'author_activity_tracking', ['author', 'subreddit'], unique=False)
    op.create_index('idx_created_at', 'author_activity_tracking', ['created_at'], unique=False)

    # Create user_spam_features table
    op.create_table('user_spam_features',
        sa.Column('username', sa.String(length=25), nullable=False),
        sa.Column('spam_score', sa.Float(), nullable=True),
        sa.Column('spam_score_confidence', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('total_posts', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('nsfw_post_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('nsfw_post_ratio', sa.Float(), nullable=True),
        sa.Column('unique_subreddit_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('adult_link_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('short_link_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('spam_subreddit_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('avg_posts_per_day', sa.Float(), nullable=True),
        sa.Column('max_posts_per_day', sa.Integer(), nullable=True),
        sa.Column('feature_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('username'),
        sa.UniqueConstraint('username')
    )
    op.create_index('idx_spam_score', 'user_spam_features', ['spam_score'], unique=False)
    op.create_index('idx_computed_at', 'user_spam_features', ['computed_at'], unique=False)

    # Create spam_subreddit_list table
    op.create_table('spam_subreddit_list',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subreddit_name', sa.String(length=25), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('added_by', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subreddit_name')
    )
    op.create_index('idx_category', 'spam_subreddit_list', ['category'], unique=False)
    op.create_index('idx_is_active', 'spam_subreddit_list', ['is_active'], unique=False)

    # Create spam_training_labels table
    op.create_table('spam_training_labels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=25), nullable=False),
        sa.Column('label', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('label_source', sa.String(length=50), nullable=False),
        sa.Column('labeled_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('labeled_by', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('feature_snapshot', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_label', 'spam_training_labels', ['label'], unique=False)
    op.create_index('idx_labeled_at', 'spam_training_labels', ['labeled_at'], unique=False)
    op.create_index('idx_label_source', 'spam_training_labels', ['label_source'], unique=False)

    # Add spam detection columns to user_review
    op.add_column('user_review', sa.Column('spam_score', sa.Float(), nullable=True))
    op.add_column('user_review', sa.Column('spam_score_confidence', sa.Float(), nullable=True))
    op.add_column('user_review', sa.Column('spam_score_updated_at', sa.DateTime(), nullable=True))
    op.add_column('user_review', sa.Column('risk_level', sa.String(length=20), nullable=True))
    op.add_column('user_review', sa.Column('is_verified_spam', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('user_review', sa.Column('is_verified_legit', sa.Boolean(), nullable=True, server_default='0'))
    op.create_index('idx_spam_score', 'user_review', ['spam_score'], unique=False)
    op.create_index('idx_risk_level', 'user_review', ['risk_level'], unique=False)

    # Add spam detection columns to monitored_sub
    op.add_column('monitored_sub', sa.Column('spam_detection_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('monitored_sub', sa.Column('spam_detection_remove_post', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('monitored_sub', sa.Column('spam_detection_ban_user', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('monitored_sub', sa.Column('spam_detection_notify_mod_mail', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('monitored_sub', sa.Column('spam_detection_score_threshold', sa.Float(), nullable=True, server_default='0.8'))
    op.add_column('monitored_sub', sa.Column('spam_detection_removal_reason', sa.String(length=300), nullable=True))
    op.add_column('monitored_sub', sa.Column('spam_detection_ban_reason', sa.String(length=300), nullable=True))

    # Insert seed data for spam_subreddit_list
    op.execute("""
        INSERT INTO spam_subreddit_list (subreddit_name, category, added_by, notes) VALUES
        ('FreeKarma4You', 'karma_farm', 'system', 'Popular karma farming subreddit'),
        ('FreeKarma4U', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('Karma4Free', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('GetFreeKarmaAnyTime', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('KarmaFarming4Pros', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('FreeKarmaForAll', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('FreeKarmaYourWay', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('EasyKarmaFarm', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('KarmaForAll', 'karma_farm', 'system', 'Karma farming subreddit'),
        ('Karma_Exchange', 'karma_farm', 'system', 'Karma exchange subreddit'),
        ('DirtySexyKikPals', 'spam_network', 'system', 'Common spam network subreddit'),
        ('KikPals', 'spam_network', 'system', 'Common spam network subreddit'),
        ('snapchat', 'spam_network', 'system', 'Promotional spam network'),
        ('SnapchatSext', 'spam_network', 'system', 'Promotional spam network')
    """)


def downgrade():
    # Remove spam detection columns from monitored_sub
    op.drop_column('monitored_sub', 'spam_detection_ban_reason')
    op.drop_column('monitored_sub', 'spam_detection_removal_reason')
    op.drop_column('monitored_sub', 'spam_detection_score_threshold')
    op.drop_column('monitored_sub', 'spam_detection_notify_mod_mail')
    op.drop_column('monitored_sub', 'spam_detection_ban_user')
    op.drop_column('monitored_sub', 'spam_detection_remove_post')
    op.drop_column('monitored_sub', 'spam_detection_enabled')

    # Remove spam detection columns from user_review
    op.drop_index('idx_risk_level', table_name='user_review')
    op.drop_index('idx_spam_score', table_name='user_review')
    op.drop_column('user_review', 'is_verified_legit')
    op.drop_column('user_review', 'is_verified_spam')
    op.drop_column('user_review', 'risk_level')
    op.drop_column('user_review', 'spam_score_updated_at')
    op.drop_column('user_review', 'spam_score_confidence')
    op.drop_column('user_review', 'spam_score')

    # Drop spam_training_labels table
    op.drop_index('idx_label_source', table_name='spam_training_labels')
    op.drop_index('idx_labeled_at', table_name='spam_training_labels')
    op.drop_index('idx_label', table_name='spam_training_labels')
    op.drop_table('spam_training_labels')

    # Drop spam_subreddit_list table
    op.drop_index('idx_is_active', table_name='spam_subreddit_list')
    op.drop_index('idx_category', table_name='spam_subreddit_list')
    op.drop_table('spam_subreddit_list')

    # Drop user_spam_features table
    op.drop_index('idx_computed_at', table_name='user_spam_features')
    op.drop_index('idx_spam_score', table_name='user_spam_features')
    op.drop_table('user_spam_features')

    # Drop author_activity_tracking table
    op.drop_index('idx_created_at', table_name='author_activity_tracking')
    op.drop_index('idx_author_subreddit', table_name='author_activity_tracking')
    op.drop_index('idx_author_created', table_name='author_activity_tracking')
    op.drop_table('author_activity_tracking')
