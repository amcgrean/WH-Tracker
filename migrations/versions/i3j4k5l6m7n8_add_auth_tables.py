"""Add app_users and otp_codes tables for passwordless email auth

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-03-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'i3j4k5l6m7n8'
down_revision = 'h2i3j4k5l6m7'
branch_labels = None
depends_on = None


def upgrade():
    # app_users — one row per person who can log in
    op.create_table(
        'app_users',
        sa.Column('id',              sa.Integer(),     nullable=False),
        sa.Column('email',           sa.String(255),   nullable=False),
        sa.Column('user_id',         sa.String(64),    nullable=True),   # ERP rep/employee ID
        sa.Column('display_name',    sa.String(128),   nullable=True),
        sa.Column('phone',           sa.String(32),    nullable=True),   # Phase 2: SMS OTP
        sa.Column('roles',           postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('is_active',       sa.Boolean(),     nullable=False, server_default='true'),
        sa.Column('created_at',      sa.DateTime(),    nullable=False, server_default=sa.func.now()),
        sa.Column('last_login_at',   sa.DateTime(),    nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_app_users_email'),
    )
    op.create_index('ix_app_users_email',     'app_users', ['email'])
    op.create_index('ix_app_users_user_id',   'app_users', ['user_id'])
    op.create_index('ix_app_users_is_active', 'app_users', ['is_active'])

    # otp_codes — short-lived codes sent during login
    op.create_table(
        'otp_codes',
        sa.Column('id',          sa.Integer(),   nullable=False),
        sa.Column('email',       sa.String(255), nullable=False),
        sa.Column('code',        sa.String(8),   nullable=False),
        sa.Column('created_at',  sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at',  sa.DateTime(),  nullable=False),
        sa.Column('used',        sa.Boolean(),   nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_otp_codes_email', 'otp_codes', ['email'])
    op.create_index('ix_otp_codes_used',  'otp_codes', ['used'])


def downgrade():
    op.drop_index('ix_otp_codes_used',        table_name='otp_codes')
    op.drop_index('ix_otp_codes_email',       table_name='otp_codes')
    op.drop_table('otp_codes')

    op.drop_index('ix_app_users_is_active',   table_name='app_users')
    op.drop_index('ix_app_users_user_id',     table_name='app_users')
    op.drop_index('ix_app_users_email',       table_name='app_users')
    op.drop_table('app_users')
