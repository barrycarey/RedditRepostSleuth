"""Modify image post current table

Revision ID: b2b67bea8e6e
Revises: 8e501b1ac31c
Create Date: 2022-06-07 18:27:55.510427

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'b2b67bea8e6e'
down_revision = '8e501b1ac31c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###

    op.add_column('reddit_image_post_current', sa.Column('reddit_image_post_db_id', sa.Integer(), nullable=True))
    op.add_column('reddit_image_post_current', sa.Column('reddit_post_db_id', sa.Integer(), nullable=True))
    op.drop_column('reddit_image_post_current', 'dhash_v')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('reddit_image_post_current', sa.Column('dhash_v', mysql.VARCHAR(length=64), nullable=True))
    op.drop_column('reddit_image_post_current', 'reddit_post_db_id')
    op.drop_column('reddit_image_post_current', 'reddit_image_post_db_id')
    # ### end Alembic commands ###
