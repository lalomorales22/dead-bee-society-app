"""Change image_url to Text

Revision ID: a7b4ee64012b
Revises: 
Create Date: 2024-10-11 07:00:38.151849

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a7b4ee64012b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Alter the 'image_url' column in the 'post' table to TEXT
    op.alter_column('post', 'image_url',
               existing_type=sa.VARCHAR(length=200),
               type_=sa.Text(),
               existing_nullable=False)


def downgrade():
    # Revert the 'image_url' column in the 'post' table back to VARCHAR(200)
    op.alter_column('post', 'image_url',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=200),
               existing_nullable=False)
