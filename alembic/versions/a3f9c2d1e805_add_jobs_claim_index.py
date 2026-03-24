"""add jobs claim index

Revision ID: a3f9c2d1e805
Revises: 1801e7588c0c
Create Date: 2026-03-24 00:00:00.000000

Adds a composite index on (status, run_at) to speed up the worker's claim
query, which filters on both columns on every poll cycle.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a3f9c2d1e805"
down_revision: Union[str, None] = "1801e7588c0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL so PostgreSQL emits CREATE INDEX IF NOT EXISTS.
    # op.create_index does not pass if_not_exists through to the PG DDL compiler.
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_status_run_at ON jobs (status, run_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_status_run_at")
