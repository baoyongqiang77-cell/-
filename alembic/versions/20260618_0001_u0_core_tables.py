"""Create U0 core persistence tables."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260618_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tenant_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tenant_type IN ('PLATFORM_OPERATOR', 'CUSTOMER_TENANT')",
            name="ck_tenants_tenant_type",
        ),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("home_tenant_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["home_tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_users_home_tenant_id", "users", ["home_tenant_id"])
    op.create_table(
        "roles",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
    )
    op.create_table(
        "user_tenant_roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("role_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["role_code"], ["roles.code"]),
        sa.UniqueConstraint(
            "user_id", "tenant_id", "role_code", name="uq_user_tenant_role"
        ),
    )
    op.create_table(
        "tenant_feature_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("feature_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint(
            "tenant_id", "feature_code", name="uq_tenant_feature_entitlement"
        ),
    )
    op.create_table(
        "tenant_data_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_tenant_id", sa.String(64), nullable=False),
        sa.Column("grantee_tenant_id", sa.String(64), nullable=False),
        sa.Column("data_scope", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["grantee_tenant_id"], ["tenants.id"]),
    )
    op.create_index(
        "ix_tenant_data_grants_owner_tenant_id",
        "tenant_data_grants",
        ["owner_tenant_id"],
    )
    op.create_index(
        "ix_tenant_data_grants_grantee_tenant_id",
        "tenant_data_grants",
        ["grantee_tenant_id"],
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("client_ip", sa.String(128)),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("code", sa.String(32)),
        sa.Column("before_status", sa.String(64)),
        sa.Column("after_status", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("http_method", sa.String(16), nullable=False),
        sa.Column("route_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(128), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint(
            "tenant_id",
            "http_method",
            "route_id",
            "idempotency_key",
            name="uq_idempotency_scope",
        ),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_request_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(
        "ix_tenant_data_grants_grantee_tenant_id",
        table_name="tenant_data_grants",
    )
    op.drop_index(
        "ix_tenant_data_grants_owner_tenant_id",
        table_name="tenant_data_grants",
    )
    op.drop_table("tenant_data_grants")
    op.drop_table("tenant_feature_entitlements")
    op.drop_table("user_tenant_roles")
    op.drop_table("roles")
    op.drop_index("ix_users_home_tenant_id", table_name="users")
    op.drop_table("users")
    op.drop_table("tenants")
