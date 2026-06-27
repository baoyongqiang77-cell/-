"""Create U1 mission dispatch receipt table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260627_0007"
down_revision = "20260627_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_dispatch_receipts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("route_version_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("device_sn", sa.String(length=128), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("external_request_id", sa.String(length=128), nullable=False),
        sa.Column("gateway_mode", sa.String(length=32), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "gateway_mode IN ('SIMULATOR', 'REAL')",
            name="ck_mission_dispatch_receipts_gateway_mode",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["missions.tenant_id", "missions.id"],
            name="fk_mission_dispatch_receipts_tenant_mission",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_mission_dispatch_receipts_tenant_id_id"
        ),
    )
    op.create_index(
        "ix_mission_dispatch_receipts_tenant_id",
        "mission_dispatch_receipts",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mission_dispatch_receipts_tenant_id",
        table_name="mission_dispatch_receipts",
    )
    op.drop_table("mission_dispatch_receipts")
