"""Create U1 GIS asset registry tables."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260627_0003"
down_revision: str | None = "20260621_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "road_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("route_code", sa.String(64), nullable=False),
        sa.Column("road_name", sa.String(255), nullable=False),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("start_stake", sa.Integer(), nullable=False),
        sa.Column("end_stake", sa.Integer(), nullable=False),
        sa.Column("geom_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("crs", sa.String(32), nullable=False),
        sa.Column("data_version", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.CheckConstraint(
            "direction IN ('UP', 'DOWN', 'BIDIRECTIONAL', 'RAMP', 'UNKNOWN')",
            name="ck_road_assets_direction",
        ),
        sa.CheckConstraint(
            "end_stake >= start_stake",
            name="ck_road_assets_stake_range",
        ),
        sa.CheckConstraint(
            "crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_road_assets_crs",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_road_assets_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "route_code",
            "direction",
            "start_stake",
            "end_stake",
            name="uq_road_assets_tenant_range",
        ),
    )
    op.create_index("ix_road_assets_tenant_id", "road_assets", ["tenant_id"])

    op.create_table(
        "bridge_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("bridge_code", sa.String(64), nullable=False),
        sa.Column("bridge_name", sa.String(255), nullable=False),
        sa.Column("route_code", sa.String(64), nullable=False),
        sa.Column("stake_no", sa.Integer(), nullable=False),
        sa.Column("geom_json", sa.JSON(), nullable=False),
        sa.Column(
            "structure_parts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("crs", sa.String(32), nullable=False),
        sa.Column("data_version", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.CheckConstraint("stake_no >= 0", name="ck_bridge_assets_stake_no"),
        sa.CheckConstraint(
            "crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_bridge_assets_crs",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_bridge_assets_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "bridge_code",
            name="uq_bridge_assets_tenant_code",
        ),
    )
    op.create_index("ix_bridge_assets_tenant_id", "bridge_assets", ["tenant_id"])

    op.create_table(
        "slope_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("slope_code", sa.String(64), nullable=False),
        sa.Column("route_code", sa.String(64), nullable=False),
        sa.Column("start_stake", sa.Integer(), nullable=False),
        sa.Column("end_stake", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("geom_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("crs", sa.String(32), nullable=False),
        sa.Column("data_version", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.CheckConstraint(
            "side IN ('LEFT', 'RIGHT', 'BOTH', 'UNKNOWN')",
            name="ck_slope_assets_side",
        ),
        sa.CheckConstraint(
            "end_stake >= start_stake",
            name="ck_slope_assets_stake_range",
        ),
        sa.CheckConstraint(
            "crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_slope_assets_crs",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_slope_assets_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "slope_code",
            name="uq_slope_assets_tenant_code",
        ),
    )
    op.create_index("ix_slope_assets_tenant_id", "slope_assets", ["tenant_id"])

    op.create_table(
        "coordinate_transforms",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source_crs", sa.String(32), nullable=False),
        sa.Column("target_crs", sa.String(32), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.CheckConstraint(
            "source_crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_coordinate_transforms_source_crs",
        ),
        sa.CheckConstraint(
            "target_crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_coordinate_transforms_target_crs",
        ),
        sa.CheckConstraint(
            "source_crs != target_crs",
            name="ck_coordinate_transforms_crs_pair",
        ),
        sa.CheckConstraint(
            "method IN ('CONFIG_ONLY', 'AFFINE', 'HELMERT', 'MANUAL_REVIEW')",
            name="ck_coordinate_transforms_method",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DEPRECATED', 'PENDING_CONFIRMATION')",
            name="ck_coordinate_transforms_status",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_crs",
            "target_crs",
            "version",
            name="uq_coordinate_transforms_scope",
        ),
    )
    op.create_index(
        "ix_coordinate_transforms_tenant_id",
        "coordinate_transforms",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_coordinate_transforms_tenant_id",
        table_name="coordinate_transforms",
    )
    op.drop_table("coordinate_transforms")
    op.drop_index("ix_slope_assets_tenant_id", table_name="slope_assets")
    op.drop_table("slope_assets")
    op.drop_index("ix_bridge_assets_tenant_id", table_name="bridge_assets")
    op.drop_table("bridge_assets")
    op.drop_index("ix_road_assets_tenant_id", table_name="road_assets")
    op.drop_table("road_assets")
