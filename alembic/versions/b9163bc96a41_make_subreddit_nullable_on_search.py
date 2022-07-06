"""make subreddit nullable on search

Revision ID: b9163bc96a41
Revises: 9ea594b18f1f
Create Date: 2022-07-05 19:03:41.086091

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'b9163bc96a41'
down_revision = '9ea594b18f1f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('repost_search', 'subreddit',
               existing_type=mysql.VARCHAR(length=100),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('repost_search', 'subreddit',
               existing_type=mysql.VARCHAR(length=100),
               nullable=False)
    # ### end Alembic commands ###
