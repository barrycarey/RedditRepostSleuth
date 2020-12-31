"""add new indexes

Revision ID: ee1c9310194b
Revises: 7332736c6ef4
Create Date: 2020-10-12 20:09:42.149805

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ee1c9310194b'
down_revision = '7332736c6ef4'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index('idx_detected_at', 'image_reposts', ['detected_at'], unique=False)
    op.create_index('idx_detected_at', 'link_reposts', ['detected_at'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_detected_at', table_name='link_reposts')
    op.drop_index('idx_detected_at', table_name='image_reposts')
    # ### end Alembic commands ###