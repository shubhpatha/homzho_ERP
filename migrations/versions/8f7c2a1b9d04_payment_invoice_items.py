"""Add editable invoice items to payments

Revision ID: 8f7c2a1b9d04
Revises: 40c79baf5cd6
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f7c2a1b9d04'
down_revision = '40c79baf5cd6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('invoice_items_json', sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column('deposit_amount', sa.Float(), nullable=False, server_default='0')
        )


def downgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_column('deposit_amount')
        batch_op.drop_column('invoice_items_json')
