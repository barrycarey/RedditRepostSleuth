"""add annoy map

Revision ID: 26e2f11e1955
Revises: cf751ec0db2c
Create Date: 2022-04-10 08:14:06.380744

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '26e2f11e1955'
down_revision = 'cf751ec0db2c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('image_index_map',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('annoy_index_id', sa.Integer(), nullable=False),
    sa.Column('reddit_post_db_id', sa.Integer(), nullable=False),
    sa.Column('index_name', sa.String(length=10), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('id_map', 'image_index_map', ['annoy_index_id', 'index_name'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('id_map', table_name='image_index_map')
    op.drop_table('image_index_map')
    # ### end Alembic commands ###