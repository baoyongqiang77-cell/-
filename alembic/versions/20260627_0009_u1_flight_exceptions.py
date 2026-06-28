"""Create U1 flight exception link table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260627_0009"
down_revision = "20260627_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flight_exception_links",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("flight_event_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("exception_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_flight_exception_links_severity",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'CLOSED')",
            name="ck_flight_exception_links_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["flight_event_id"], ["flight_events.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["missions.tenant_id", "missions.id"],
            name="fk_flight_exception_links_tenant_mission",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "flight_event_id",
            name="uq_flight_exception_links_tenant_event",
        ),
    )
    op.create_index(
        "ix_flight_exception_links_tenant_id",
        "flight_exception_links",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_flight_exception_links_tenant_id",
        table_name="flight_exception_links",
    )
    op.drop_table("flight_exception_links")
