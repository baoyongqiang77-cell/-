"""Add U2 media ingest metadata and chunks."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260628_0011"
down_revision = "20260628_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_files") as batch:
        batch.alter_column(
            "source_event_id",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        batch.add_column(sa.Column("source_type", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column("original_filename", sa.String(length=255), nullable=True)
        )
        batch.add_column(sa.Column("mime_type", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("size_bytes", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("failure_reason", sa.String(length=512), nullable=True))
        batch.create_unique_constraint(
            "uq_media_files_tenant_id",
            ["tenant_id", "id"],
        )

    op.create_table(
        "media_chunks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("media_file_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_total", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('UPLOADED', 'CHECKSUM_FAILED')",
            name="ck_media_chunks_status",
        ),
        sa.CheckConstraint(
            "chunk_index >= 1 AND chunk_total >= chunk_index",
            name="ck_media_chunks_index_range",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "media_file_id"],
            ["media_files.tenant_id", "media_files.id"],
            name="fk_media_chunks_tenant_media_file",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "media_file_id",
            "chunk_index",
            name="uq_media_chunks_tenant_media_file_index",
        ),
    )
    op.create_index("ix_media_chunks_tenant_id", "media_chunks", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_media_chunks_tenant_id", table_name="media_chunks")
    op.drop_table("media_chunks")

    with op.batch_alter_table("media_files") as batch:
        batch.drop_constraint("uq_media_files_tenant_id", type_="unique")
        batch.drop_column("failure_reason")
        batch.drop_column("captured_at")
        batch.drop_column("size_bytes")
        batch.drop_column("mime_type")
        batch.drop_column("original_filename")
        batch.drop_column("source_type")
        batch.alter_column(
            "source_event_id",
            existing_type=sa.String(length=64),
            nullable=False,
        )
