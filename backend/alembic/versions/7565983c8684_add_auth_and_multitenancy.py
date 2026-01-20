"""add_auth_and_multitenancy

Revision ID: 7565983c8684
Revises: d5d0d99d2cf0
Create Date: 2026-01-19 17:21:45.199199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7565983c8684'
down_revision: Union[str, Sequence[str], None] = 'd5d0d99d2cf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add authentication fields to users and user_id to owned tables."""

    # Add authentication fields to users table
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('is_email_verified', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('users', sa.Column('email_verification_token', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('password_reset_token', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('password_reset_expires', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), server_default='0', nullable=True))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('role', sa.String(20), server_default='user', nullable=True))

    # Add user_id foreign key to companies table
    op.add_column('companies', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index('ix_companies_user_id', 'companies', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_companies_user_id',
        'companies', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # Add user_id foreign key to jobs table
    op.add_column('jobs', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_jobs_user_id',
        'jobs', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # Add user_id foreign key to contacts table
    op.add_column('contacts', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index('ix_contacts_user_id', 'contacts', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_contacts_user_id',
        'contacts', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Remove authentication fields and user_id columns."""

    # Remove user_id from contacts
    op.drop_constraint('fk_contacts_user_id', 'contacts', type_='foreignkey')
    op.drop_index('ix_contacts_user_id', table_name='contacts')
    op.drop_column('contacts', 'user_id')

    # Remove user_id from jobs
    op.drop_constraint('fk_jobs_user_id', 'jobs', type_='foreignkey')
    op.drop_index('ix_jobs_user_id', table_name='jobs')
    op.drop_column('jobs', 'user_id')

    # Remove user_id from companies
    op.drop_constraint('fk_companies_user_id', 'companies', type_='foreignkey')
    op.drop_index('ix_companies_user_id', table_name='companies')
    op.drop_column('companies', 'user_id')

    # Remove auth fields from users
    op.drop_column('users', 'role')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'password_reset_expires')
    op.drop_column('users', 'password_reset_token')
    op.drop_column('users', 'email_verification_token')
    op.drop_column('users', 'is_email_verified')
    op.drop_column('users', 'password_hash')
