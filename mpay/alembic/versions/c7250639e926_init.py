"""init

Revision ID: c7250639e926
Revises:
Create Date: 2024-11-02 22:08:35.651931

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7250639e926'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('agents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agents')),
    sa.UniqueConstraint('name', name=op.f('uq_agents_name')),
    mysql_collate='utf8mb4_unicode_520_ci',
    mysql_default_charset='utf8mb4'
    )

    op.create_table('currencies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('iso_4217', sa.String(length=3), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_currencies')),
    sa.UniqueConstraint('iso_4217', name=op.f('uq_currencies_iso_4217')),
    mysql_collate='utf8mb4_unicode_520_ci',
    mysql_default_charset='utf8mb4'
    )

    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    # MySQL does not like CHECK on AUTO_INCREMENT column, hence the ddl_if
    sa.CheckConstraint('parent_id <> id', name=op.f('ck_tags_parent_not_self')).ddl_if(dialect="sqlite"),
    sa.ForeignKeyConstraint(['parent_id'], ['tags.id'], name=op.f('fk_tags_parent_id_tags')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tags')),
    sa.UniqueConstraint('name', 'parent_id', name=op.f('uq_tags_name')),
    mysql_collate='utf8mb4_unicode_520_ci',
    mysql_default_charset='utf8mb4'
    )

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('balance', sa.Numeric(precision=9, scale=3), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('name', name=op.f('uq_users_name')),
    mysql_collate='utf8mb4_unicode_520_ci',
    mysql_default_charset='utf8mb4'
    )

    op.create_table('standing_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('user_from_id', sa.Integer(), nullable=False),
    sa.Column('user_to_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=9, scale=3), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('rrule_str', sa.String(length=255), nullable=False),
    sa.Column('dt_next_utc', sa.DateTime(), nullable=True),
    sa.Column('dt_created_utc', sa.DateTime(), nullable=False),
    sa.CheckConstraint('amount > 0', name=op.f('ck_standing_orders_amount_gt_zero')),
    sa.CheckConstraint('user_from_id <> user_to_id', name=op.f('ck_standing_orders_user_from_to_different')),
    sa.ForeignKeyConstraint(['user_from_id'], ['users.id'], name=op.f('fk_standing_orders_user_from_id_users')),
    sa.ForeignKeyConstraint(['user_to_id'], ['users.id'], name=op.f('fk_standing_orders_user_to_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_standing_orders')),
    sa.UniqueConstraint('name', 'user_from_id', name=op.f('uq_standing_orders_name')),
    mysql_collate='utf8mb4_unicode_520_ci',
    mysql_default_charset='utf8mb4'
    )

    op.create_table('transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_from_id', sa.Integer(), nullable=False),
    sa.Column('user_to_id', sa.Integer(), nullable=False),
    sa.Column('original_amount', sa.Numeric(precision=9, scale=3), nullable=True),
    sa.Column('original_currency_id', sa.Integer(), nullable=True),
    sa.Column('converted_amount', sa.Numeric(precision=9, scale=3), nullable=False),
    sa.Column('standing_order_id', sa.Integer(), nullable=True),
    sa.Column('agent_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('dt_created_utc', sa.DateTime(), nullable=False),
    sa.Column('dt_due_utc', sa.DateTime(), nullable=False),
    sa.CheckConstraint('(original_currency_id IS NULL) = (original_amount IS NULL)', name=op.f('ck_transactions_both_original_amount_and_currency')),
    sa.CheckConstraint('dt_due_utc <= dt_created_utc', name=op.f('ck_transactions_dt_due_not_in_future')),
    sa.CheckConstraint('user_from_id <> user_to_id', name=op.f('ck_transactions_user_from_to_different')),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_transactions_agent_id_agents')),
    sa.ForeignKeyConstraint(['original_currency_id'], ['currencies.id'], name=op.f('fk_transactions_original_currency_id_currencies')),
    sa.ForeignKeyConstraint(['standing_order_id'], ['standing_orders.id'], name=op.f('fk_transactions_standing_order_id_standing_orders')),
    sa.ForeignKeyConstraint(['user_from_id'], ['users.id'], name=op.f('fk_transactions_user_from_id_users')),
    sa.ForeignKeyConstraint(['user_to_id'], ['users.id'], name=op.f('fk_transactions_user_to_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transactions')),
    mysql_collate='utf8mb4_unicode_520_ci',
    mysql_default_charset='utf8mb4'
    )

    op.create_table('transactions_tags',
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], name=op.f('fk_transactions_tags_tag_id_tags'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], name=op.f('fk_transactions_tags_transaction_id_transactions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('transaction_id', 'tag_id', name=op.f('pk_transactions_tags'))
    )

    op.execute("""
    CREATE TRIGGER update_balance_update AFTER UPDATE ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE users SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
        UPDATE users SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE users SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)

    op.execute("""
    CREATE TRIGGER update_balance_insert AFTER INSERT ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE users SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)

    op.execute("""
    CREATE TRIGGER update_balance_delete AFTER DELETE ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE users SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
    END;
    """)


def downgrade() -> None:
    op.drop_table('transactions_tags')
    op.drop_table('transactions')
    op.drop_table('standing_orders')
    op.drop_table('users')
    op.drop_table('tags')
    op.drop_table('currencies')
    op.drop_table('agents')

    # Triggers are dropped automatically when the corresponding table is
    # dropped.
