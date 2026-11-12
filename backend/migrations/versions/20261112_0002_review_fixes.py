"""review fixes: comments.edited_at, one open report per user per comment

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12

* comments.edited_at: the "edited" flag was derived from updated_at, which also changes when a
  comment gets a like or a reply (onupdate). Now only an explicit edit sets edited_at.
* reports: the moderation queue could be spammed with duplicate open reports on one comment.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("comments", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "uq_reports_open_per_user_comment",
        "reports",
        ["reporter_id", "comment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND comment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_reports_open_per_user_comment", table_name="reports")
    op.drop_column("comments", "edited_at")
