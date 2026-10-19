"""Persist generated classroom lecture packs per lesson.

Revision ID: 0058_lesson_classroom_packs
Revises: 0057_flashcard_review_receipts
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0058_lesson_classroom_packs"
down_revision = "0057_flashcard_review_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_classroom_packs",
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("generator_version", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lesson_id"),
    )


def downgrade() -> None:
    op.drop_table("lesson_classroom_packs")
