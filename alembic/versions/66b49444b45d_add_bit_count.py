"""Add bit count

Revision ID: 66b49444b45d
Revises: f1b37c0e9d53
Create Date: 2019-02-13 00:01:22.717779

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '66b49444b45d'
down_revision = 'f1b37c0e9d53'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('reddit_post', sa.Column('images_bits_set', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_reddit_post_images_bits_set'), 'reddit_post', ['images_bits_set'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_reddit_post_images_bits_set'), table_name='reddit_post')
    op.drop_column('reddit_post', 'images_bits_set')
    # ### end Alembic commands ###