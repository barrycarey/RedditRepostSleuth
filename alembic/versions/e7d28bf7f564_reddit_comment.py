"""reddit comment

Revision ID: e7d28bf7f564
Revises: e7b3e28cbe72
Create Date: 2021-02-01 19:26:38.864105

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7d28bf7f564'
down_revision = 'e7b3e28cbe72'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('reddit_comments', sa.Column('text_hash', sa.String(length=32), nullable=True))
    op.create_index('idx_comment_hash', 'reddit_comments', ['text_hash'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_comment_hash', table_name='reddit_comments')
    op.drop_column('reddit_comments', 'text_hash')
    # ### end Alembic commands ###
