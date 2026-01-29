"""Add easy_karma subreddits to spam_subreddit_list

Revision ID: 20260129_easy_karma
Revises: 20260127_add_post_scanning
Create Date: 2026-01-29

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '20260129_easy_karma'
down_revision = '20260127_add_post_scanning'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO spam_subreddit_list (subreddit_name, category, is_active, notes) VALUES
        -- High-Volume Repost Targets (Bot farming grounds)
        ('oddlysatisfying', 'easy_karma', 1, 'Heavily botted'),
        ('todayilearned', 'easy_karma', 1, 'Heavily botted'),
        ('MadeMeSmile', 'easy_karma', 1, 'Easy karma target'),
        ('nextfuckinglevel', 'easy_karma', 1, 'Easy karma target'),
        ('aww', 'easy_karma', 1, 'Easy karma target'),
        ('pics', 'easy_karma', 1, 'Easy karma target'),
        ('funny', 'easy_karma', 1, 'Easy karma target'),
        ('memes', 'easy_karma', 1, 'Easy karma target'),
        ('HolUp', 'easy_karma', 1, 'Easy karma target'),
        ('ThatsInsane', 'easy_karma', 1, 'Easy karma target'),
        -- Celebrity/Easy Photo Karma (Low moderation)
        ('KylieJenner', 'easy_karma', 1, 'Low moderation'),
        ('KimKardashianPics', 'easy_karma', 1, 'Low moderation'),
        ('Rihanna', 'easy_karma', 1, 'Low moderation'),
        ('Kanye', 'easy_karma', 1, 'Low moderation'),
        ('CelebrityFeet', 'easy_karma', 1, 'Low moderation')
    """)


def downgrade():
    op.execute("""
        DELETE FROM spam_subreddit_list WHERE category = 'easy_karma'
    """)
