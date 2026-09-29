"""Assign document owners without exposing legacy unowned uploads."""
from sqlalchemy import inspect, text


def migrate_document_ownership(connection):
    inspector = inspect(connection)
    if not inspector.has_table("documents"):
        return
    columns = {column["name"] for column in inspector.get_columns("documents")}
    if "user_id" not in columns:
        connection.execute(text(
            "ALTER TABLE documents ADD COLUMN user_id INTEGER REFERENCES users(id)"
        ))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id)"
    ))
    # A standalone legacy upload has no trustworthy owner; leave it inaccessible.
    connection.execute(text("""
        UPDATE documents SET user_id = (
            SELECT jobs.user_id FROM jobs WHERE jobs.id = documents.job_id
        ) WHERE user_id IS NULL AND job_id IS NOT NULL
    """))
