"""comment permalink

Revision ID: c8f1e18b7ebc
Revises: e7d28bf7f564
Create Date: 2021-02-01 20:09:34.600293

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8f1e18b7ebc'
down_revision = 'e7d28bf7f564'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('reddit_comments', sa.Column('perma_link', sa.String(length=300), nullable=True))
    op.create_index('idx_comment_id', 'reddit_comments', ['comment_id'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_comment_id', table_name='reddit_comments')
    op.drop_column('reddit_comments', 'perma_link')
    # ### end Alembic commands ###
