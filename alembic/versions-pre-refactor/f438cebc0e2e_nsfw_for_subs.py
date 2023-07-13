"""nsfw for subs

Revision ID: f438cebc0e2e
Revises: 505caf95a77e
Create Date: 2021-02-26 08:18:01.651250

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'f438cebc0e2e'
down_revision = '505caf95a77e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('reddit_image_search', 'search_results')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('reddit_image_search', sa.Column('search_results', mysql.MEDIUMTEXT(charset='utf8mb4', collation='utf8mb4_general_ci'), nullable=True))
    # ### end Alembic commands ###