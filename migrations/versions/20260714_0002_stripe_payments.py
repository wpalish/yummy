"""Stripe payment state machine.

Revision ID: 20260714_0002
Revises: 20260714_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260714_0002"
down_revision = "20260714_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_status", sa.Text(), nullable=False, server_default="paid"))
    op.add_column("orders", sa.Column("reservation_expires_at", sa.Text()))
    op.create_table("payments",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("order_id", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", sa.Text()), sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False), sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("checkout_session_id", sa.Text(), unique=True),
        sa.Column("payment_intent_id", sa.Text(), unique=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("reservation_expires_at", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False), sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('pending','paid','failed','expired','refunded')", name="ck_payment_status"),
        sa.CheckConstraint("amount_minor > 0", name="ck_payment_amount"))
    op.create_index("ix_payments_status", "payments", ["status", "reservation_expires_at"])
    op.create_index("ix_payments_user", "payments", ["user_id", "created_at"])
    op.create_table("stripe_events",
        sa.Column("event_id", sa.Text(), primary_key=True), sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False), sa.Column("received_at", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.Text()), sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()))


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_table("payments")
    op.drop_column("orders", "reservation_expires_at")
    op.drop_column("orders", "payment_status")
