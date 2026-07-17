"""Partner merchant accounts and commission accounting.

Revision ID: 20260714_0004
Revises: 20260714_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20260714_0004"
down_revision = "20260714_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("partner_payment_accounts",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False), sa.Column("merchant_reference", sa.Text(), nullable=False),
        sa.Column("point_of_service_id", sa.Text()), sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("payments_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refunds_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False), sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.Text()), sa.Column("verified_by", sa.Text()),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.UniqueConstraint("partner_id", "provider", name="uq_partner_provider"),
        sa.CheckConstraint("provider IN ('kaspi','stripe')", name="ck_payment_provider"),
        sa.CheckConstraint("status IN ('pending','active','suspended')", name="ck_merchant_status"))
    op.create_index("ix_partner_payment_accounts", "partner_payment_accounts", ["partner_id", "status"])
    op.create_table("commission_rules",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("rate_basis_points", sa.Integer(), nullable=False), sa.Column("valid_from", sa.Text(), nullable=False),
        sa.Column("valid_to", sa.Text()), sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False), sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.CheckConstraint("rate_basis_points BETWEEN 0 AND 5000", name="ck_commission_rate"))
    op.create_index("ix_commission_rules", "commission_rules", ["partner_id", "valid_from"])
    op.create_table("commission_invoices",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("period_from", sa.Text(), nullable=False), sa.Column("period_to", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False), sa.Column("status", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.Text()), sa.Column("due_at", sa.Text()), sa.Column("paid_at", sa.Text()),
        sa.Column("document_number", sa.Text(), unique=True), sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]))
    op.create_index("ix_commission_invoices", "commission_invoices", ["partner_id", "status"])
    op.create_table("commission_ledger",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("order_id", sa.Text(), nullable=False, unique=True), sa.Column("payment_id", sa.Text(), nullable=False),
        sa.Column("gross_amount_minor", sa.Integer(), nullable=False),
        sa.Column("commission_rate_bps", sa.Integer(), nullable=False),
        sa.Column("commission_amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False), sa.Column("invoice_id", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False), sa.Column("reversed_at", sa.Text()),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["commission_invoices.id"]),
        sa.CheckConstraint("commission_rate_bps BETWEEN 0 AND 5000", name="ck_ledger_rate"))
    op.create_index("ix_commission_ledger", "commission_ledger", ["partner_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_table("commission_ledger")
    op.drop_table("commission_invoices")
    op.drop_table("commission_rules")
    op.drop_table("partner_payment_accounts")
