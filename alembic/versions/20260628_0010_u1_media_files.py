"""Create U1 media file table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260628_0010"
down_revision = "20260627_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_files",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=64), nullable=False),
        sa.Column("media_id", sa.String(length=128), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("checksum", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "media_type IN ('VIDEO', 'IMAGE', 'THUMBNAIL')",
            name="ck_media_files_media_type",
        ),
        sa.CheckConstraint(
            "status IN ('CAPTURED', 'UPLOADING', 'UPLOAD_FAILED', 'REGISTERING', 'READY', 'REJECTED', 'FRAME_EXTRACTING', 'FRAME_READY', 'ARCHIVED', 'DELETED')",
            name="ck_media_files_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["flight_events.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["missions.tenant_id", "missions.id"],
            name="fk_media_files_tenant_mission",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_event_id",
            name="uq_media_files_tenant_source_event",
        ),
    )
    op.create_index("ix_media_files_tenant_id", "media_files", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_media_files_tenant_id", table_name="media_files")
    op.drop_table("media_files")
