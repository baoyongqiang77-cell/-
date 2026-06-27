"""Create U1 route management tables."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260627_0004"
down_revision: str | None = "20260627_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("route_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "id", name="uq_routes_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "route_code", name="uq_routes_tenant_code"),
    )
    op.create_index("ix_routes_tenant_id", "routes", ["tenant_id"])

    op.create_table(
        "route_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("route_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("route_file_uri", sa.String(512), nullable=False),
        sa.Column("route_format", sa.String(32), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("path_geom_json", sa.JSON(), nullable=False),
        sa.Column(
            "asset_bindings",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "validation_report",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("dji_route_id", sa.String(128)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "route_id"],
            ["routes.tenant_id", "routes.id"],
            name="fk_route_versions_tenant_route",
        ),
        sa.CheckConstraint(
            "route_format IN ('DJI_WPML', 'KML', 'GEOJSON', 'PENDING_CONFIRMATION')",
            name="ck_route_versions_route_format",
        ),
        sa.CheckConstraint(
            "checksum LIKE 'sha256:%'",
            name="ck_route_versions_checksum",
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_route_versions_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "route_id",
            "version",
            name="uq_route_versions_tenant_route_version",
        ),
    )
    op.create_index("ix_route_versions_tenant_id", "route_versions", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_route_versions_tenant_id", table_name="route_versions")
    op.drop_table("route_versions")
    op.drop_index("ix_routes_tenant_id", table_name="routes")
    op.drop_table("routes")
