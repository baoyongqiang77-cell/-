"""Create U1 mission creation table."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260627_0005"
down_revision: str | None = "20260627_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MISSION_STATUS_SQL = (
    "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'DISPATCHING', "
    "'DISPATCHED', 'EXECUTING', 'PAUSED', 'RETURNING', 'LOST_LINK', "
    "'COMPLETED', 'ABORTED', 'MEDIA_SYNCING', 'PARTIAL_MEDIA_READY', "
    "'MEDIA_READY', 'ANALYSIS_READY', 'CANCELLED', 'REJECTED', 'EXPIRED', "
    "'DISPATCH_FAILED', 'SYNC_FAILED', 'ARCHIVED')"
)


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("route_id", sa.String(64), nullable=False),
        sa.Column("route_version_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("dock_id", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("schedule_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inspection_targets", sa.JSON(), nullable=False),
        sa.Column("media_policy", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "route_id"],
            ["routes.tenant_id", "routes.id"],
            name="fk_missions_tenant_route",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "route_version_id"],
            ["route_versions.tenant_id", "route_versions.id"],
            name="fk_missions_tenant_route_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_missions_tenant_device",
        ),
        sa.ForeignKeyConstraint(
            ["dock_id"],
            ["docks.id"],
            name="fk_missions_dock",
        ),
        sa.CheckConstraint(MISSION_STATUS_SQL, name="ck_missions_status"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_missions_tenant_id_id"),
    )
    op.create_index("ix_missions_tenant_id", "missions", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_missions_tenant_id", table_name="missions")
    op.drop_table("missions")
