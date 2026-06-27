"""Create U1 flight event table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260627_0008"
down_revision = "20260627_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flight_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("event_code", sa.String(length=64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_sn", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["missions.tenant_id", "missions.id"],
            name="fk_flight_events_tenant_mission",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_flight_events_tenant_id", "flight_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_flight_events_tenant_id", table_name="flight_events")
    op.drop_table("flight_events")
