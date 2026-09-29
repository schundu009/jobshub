"""Add document ownership and backfill owners from linked jobs."""
from alembic import op
from migrations.document_ownership import migrate_document_ownership

revision = "b742a910d621"
down_revision = "7565983c8684"
branch_labels = None
depends_on = None


def upgrade():
    migrate_document_ownership(op.get_bind())


def downgrade():
    op.drop_index("ix_documents_user_id", table_name="documents")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("user_id")
