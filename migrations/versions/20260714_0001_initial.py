"""Initial PostgreSQL/SQLite schema for Yummy 0.10.

Revision ID: 20260714_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20260714_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("email_verified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pw_hash", sa.Text(), nullable=False), sa.Column("role", sa.Text(), nullable=False),
        sa.Column("brand_name", sa.Text()), sa.Column("address", sa.Text()), sa.Column("district", sa.Text()),
        sa.Column("partner_id", sa.Text()), sa.Column("partner_status", sa.Text()),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("token_ver", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("terms_accepted_at", sa.Text()), sa.Column("terms_version", sa.Text()),
        sa.Column("mfa_secret", sa.Text()),
        sa.Column("mfa_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mfa_last_counter", sa.Integer(), nullable=False, server_default="-1"),
        sa.CheckConstraint("role IN ('customer','partner','admin')", name="ck_users_role"),
        sa.CheckConstraint("partner_status IS NULL OR partner_status IN ('pending','approved','suspended','rejected')", name="ck_partner_status"),
    )
    op.create_index("ux_users_partner", "users", ["partner_id"], unique=True,
                    postgresql_where=sa.text("partner_id IS NOT NULL"), sqlite_where=sa.text("partner_id IS NOT NULL"))
    op.create_table("refresh_tokens",
        sa.Column("token_hash", sa.Text(), primary_key=True), sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("family_id", sa.Text()), sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked", sa.Integer(), nullable=False, server_default="0"), sa.Column("used_at", sa.BigInteger()),
        sa.Column("mfa_verified", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"))
    op.create_index("ix_refresh_user", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_family", "refresh_tokens", ["family_id"])
    op.create_table("mfa_recovery_codes",
        sa.Column("user_id", sa.Text(), nullable=False), sa.Column("code_hash", sa.Text(), primary_key=True),
        sa.Column("used_at", sa.BigInteger()), sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"))
    op.create_table("action_tokens",
        sa.Column("token_hash", sa.Text(), primary_key=True), sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False), sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("used_at", sa.BigInteger()), sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("purpose IN ('verify_email','password_reset')", name="ck_action_purpose"))
    op.create_index("ix_action_user", "action_tokens", ["user_id", "purpose"])

    op.create_table("partners",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("name", sa.Text(), nullable=False),
        sa.Column("district", sa.Text(), nullable=False), sa.Column("address", sa.Text(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False), sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False), sa.Column("owner_user_id", sa.Text()))
    op.create_index("ux_partners_owner", "partners", ["owner_user_id"], unique=True,
                    postgresql_where=sa.text("owner_user_id IS NOT NULL"), sqlite_where=sa.text("owner_user_id IS NOT NULL"))
    op.create_table("boxes",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False), sa.Column("title", sa.Text(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False), sa.Column("value_est", sa.Integer(), nullable=False),
        sa.Column("qty_total", sa.Integer(), nullable=False), sa.Column("qty_left", sa.Integer(), nullable=False),
        sa.Column("pickup_from", sa.Text(), nullable=False), sa.Column("pickup_to", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.CheckConstraint("qty_total >= 0 AND qty_left >= 0 AND qty_left <= qty_total", name="ck_box_qty"))
    op.create_index("ix_boxes_partner", "boxes", ["partner_id"])
    op.create_index("ix_boxes_status", "boxes", ["status", "qty_left"])
    op.create_table("orders",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("box_id", sa.Text(), nullable=False), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False), sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("user_name", sa.Text(), nullable=False), sa.Column("user_phone", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False), sa.Column("pickup_from", sa.Text(), nullable=False),
        sa.Column("pickup_to", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text()), sa.ForeignKeyConstraint(["box_id"], ["boxes.id"]),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]))
    op.create_index("ix_orders_partner", "orders", ["partner_id", "created_at"])
    op.create_index("ix_orders_user", "orders", ["user_id", "created_at"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_table("reviews",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("order_id", sa.Text(), nullable=False, unique=True), sa.Column("user_id", sa.Text()),
        sa.Column("author_name", sa.Text(), nullable=False), sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False, server_default="approved"),
        sa.Column("reject_reason", sa.Text()), sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]), sa.ForeignKeyConstraint(["order_id"], ["orders.id"]))
    op.create_index("ix_reviews_partner", "reviews", ["partner_id", "status", "created_at"])
    op.create_table("refund_requests",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("order_id", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", sa.Text(), nullable=False), sa.Column("partner_id", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("resolution", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False), sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("resolved_by", sa.Text()), sa.ForeignKeyConstraint(["order_id"], ["orders.id"]))
    op.create_index("ix_refunds_user", "refund_requests", ["user_id", "created_at"])
    op.create_index("ix_refunds_status", "refund_requests", ["status", "created_at"])


def downgrade() -> None:
    for table in ("refund_requests", "reviews", "orders", "boxes", "partners",
                  "action_tokens", "mfa_recovery_codes", "refresh_tokens", "users"):
        op.drop_table(table)
