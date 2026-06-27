"""Create U1 device and dock registry tables."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260621_0002"
down_revision: str | None = "20260618_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("device_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("manufacturer", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("serial_number", sa.String(128), nullable=False),
        sa.Column("firmware_version", sa.String(128)),
        sa.Column("status", sa.String(16)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.CheckConstraint(
            "device_type IN ('DOCK', 'DRONE', 'PAYLOAD', 'EDGE_NODE')",
            name="ck_devices_device_type",
        ),
        sa.CheckConstraint(
            "status IS NULL OR status IN ('ONLINE', 'OFFLINE')",
            name="ck_devices_status",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_devices_tenant_id_id"),
        sa.UniqueConstraint("serial_number", name="uq_devices_serial_number"),
    )
    op.create_index("ix_devices_tenant_id", "devices", ["tenant_id"])
    op.create_table(
        "docks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("bound_drone_device_id", sa.String(64)),
        sa.Column("edge_node_device_id", sa.String(64)),
        sa.Column(
            "environment_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_device",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bound_drone_device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_drone",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "edge_node_device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_edge_node",
        ),
        sa.UniqueConstraint("device_id", name="uq_docks_device_id"),
    )
    op.create_index("ix_docks_tenant_id", "docks", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_docks_tenant_id", table_name="docks")
    op.drop_table("docks")
    op.drop_index("ix_devices_tenant_id", table_name="devices")
    op.drop_table("devices")
