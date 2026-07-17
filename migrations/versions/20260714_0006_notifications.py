"""Encrypted transactional notification outbox and admin audit.
Revision ID: 20260714_0006
Revises: 20260714_0005
"""
from alembic import op
import sqlalchemy as sa
revision = "20260714_0006"
down_revision = "20260714_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("notification_outbox",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("dedupe_key", sa.Text(), nullable=False, unique=True),
        sa.Column("recipient_email", sa.Text(), nullable=False), sa.Column("template", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.Text()), sa.Column("last_error", sa.Text()),
        sa.CheckConstraint("status IN ('pending','retry','sent','dead')", name="ck_outbox_status"))
    op.create_index("ix_outbox_due", "notification_outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("notification_outbox")
