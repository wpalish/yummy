"""Invitation-only partner staff access.

Revision ID: 20260714_0003
Revises: 20260714_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260714_0003"
down_revision = "20260714_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("partner_role", sa.Text()))
    op.execute("UPDATE users SET partner_role='owner' WHERE role='partner'")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ux_users_partner")
        batch.create_index("ix_users_partner", ["partner_id"])
        batch.create_check_constraint(
            "ck_partner_role",
            "partner_role IS NULL OR partner_role IN ('owner','manager','cashier')",
        )
    op.create_table("staff_invitations",
        sa.Column("token_hash", sa.Text(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("partner_id", sa.Text()),
        sa.Column("partner_role", sa.Text(), nullable=False),
        sa.Column("brand_name", sa.Text()), sa.Column("address", sa.Text()),
        sa.Column("district", sa.Text()), sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("used_at", sa.BigInteger()), sa.Column("invited_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("partner_role IN ('owner','manager','cashier')", name="ck_invite_role"))
    op.create_index("ix_invites_email", "staff_invitations", ["email", "used_at"])


def downgrade() -> None:
    op.drop_table("staff_invitations")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_partner_role", type_="check")
        batch.drop_index("ix_users_partner")
        batch.create_index("ux_users_partner", ["partner_id"], unique=True,
                           postgresql_where=sa.text("partner_id IS NOT NULL"),
                           sqlite_where=sa.text("partner_id IS NOT NULL"))
        batch.drop_column("partner_role")
