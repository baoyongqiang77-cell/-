"""Create U1 mission approval table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260627_0006"
down_revision = "20260627_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_approvals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("external_system", sa.String(length=128), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("external_status", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("callback_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("submitted_by", sa.String(length=64), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("decision_comment", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED')",
            name="ck_mission_approvals_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["missions.tenant_id", "missions.id"],
            name="fk_mission_approvals_tenant_mission",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mission_approvals_tenant_id_id"),
    )
    op.create_index("ix_mission_approvals_tenant_id", "mission_approvals", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_mission_approvals_tenant_id", table_name="mission_approvals")
    op.drop_table("mission_approvals")
