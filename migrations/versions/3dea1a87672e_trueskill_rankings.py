"""trueskill rankings

Revision ID: 3dea1a87672e
Revises: bf7ab257ce86
Create Date: 2020-09-24 22:17:22.424957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3dea1a87672e'
down_revision = 'bf7ab257ce86'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('match_score', sa.Column('entry_rating', sa.Integer(), nullable=True))
    op.add_column('match_score', sa.Column('exit_rating', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('match_score', 'exit_rating')
    op.drop_column('match_score', 'entry_rating')
    # ### end Alembic commands ###