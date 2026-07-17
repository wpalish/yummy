"""Persistent security/admin audit events.
Revision ID: 20260714_0005
Revises: 20260714_0004
"""
from alembic import op
import sqlalchemy as sa
revision = "20260714_0005"
down_revision = "20260714_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("audit_events",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text()), sa.Column("target_type", sa.Text()),
        sa.Column("target_id", sa.Text()), sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False))
    op.create_index("ix_audit_created", "audit_events", ["created_at", "event_type"])


def downgrade() -> None:
    op.drop_table("audit_events")
