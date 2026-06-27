from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TenantModel(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "tenant_type IN ('PLATFORM_OPERATOR', 'CUSTOMER_TENANT')",
            name="ck_tenants_tenant_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    home_tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RoleModel(Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class UserTenantRoleModel(Base):
    __tablename__ = "user_tenant_roles"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "tenant_id", "role_code", name="uq_user_tenant_role"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    role_code: Mapped[str] = mapped_column(ForeignKey("roles.code"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class TenantFeatureEntitlementModel(Base):
    __tablename__ = "tenant_feature_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "feature_code", name="uq_tenant_feature_entitlement"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    feature_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class TenantDataGrantModel(Base):
    __tablename__ = "tenant_data_grants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    grantee_tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    data_scope: Mapped[dict] = mapped_column(JSON, nullable=False)
    purpose: Mapped[list] = mapped_column(JSON, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_request_id", "request_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    client_ip: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str | None] = mapped_column(String(32))
    before_status: Mapped[str | None] = mapped_column(String(64))
    after_status: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "http_method",
            "route_id",
            "idempotency_key",
            name="uq_idempotency_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    http_method: Mapped[str] = mapped_column(String(16), nullable=False)
    route_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DeviceModel(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "device_type IN ('DOCK', 'DRONE', 'PAYLOAD', 'EDGE_NODE')",
            name="ck_devices_device_type",
        ),
        CheckConstraint(
            "status IS NULL OR status IN ('ONLINE', 'OFFLINE')",
            name="ck_devices_status",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_devices_tenant_id_id"),
        UniqueConstraint("serial_number", name="uq_devices_serial_number"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(16))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class DockModel(Base):
    __tablename__ = "docks"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_docks_device_id"),
        ForeignKeyConstraint(
            ["tenant_id", "device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_device",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bound_drone_device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_drone",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "edge_node_device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_edge_node",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_drone_device_id: Mapped[str | None] = mapped_column(String(64))
    edge_node_device_id: Mapped[str | None] = mapped_column(String(64))
    environment_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RoadAssetModel(Base):
    __tablename__ = "road_assets"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('UP', 'DOWN', 'BIDIRECTIONAL', 'RAMP', 'UNKNOWN')",
            name="ck_road_assets_direction",
        ),
        CheckConstraint("end_stake >= start_stake", name="ck_road_assets_stake_range"),
        CheckConstraint(
            "crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_road_assets_crs",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_road_assets_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "route_code",
            "direction",
            "start_stake",
            "end_stake",
            name="uq_road_assets_tenant_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    road_name: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    start_stake: Mapped[int] = mapped_column(Integer, nullable=False)
    end_stake: Mapped[int] = mapped_column(Integer, nullable=False)
    geom_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(
        String(128), nullable=False, default="MANUAL_IMPORT"
    )
    crs: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING_CONFIRMATION"
    )
    data_version: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class BridgeAssetModel(Base):
    __tablename__ = "bridge_assets"
    __table_args__ = (
        CheckConstraint("stake_no >= 0", name="ck_bridge_assets_stake_no"),
        CheckConstraint(
            "crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_bridge_assets_crs",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_bridge_assets_tenant_id_id"),
        UniqueConstraint("tenant_id", "bridge_code", name="uq_bridge_assets_tenant_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    bridge_code: Mapped[str] = mapped_column(String(64), nullable=False)
    bridge_name: Mapped[str] = mapped_column(String(255), nullable=False)
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    stake_no: Mapped[int] = mapped_column(Integer, nullable=False)
    geom_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    structure_parts: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    source: Mapped[str] = mapped_column(
        String(128), nullable=False, default="MANUAL_IMPORT"
    )
    crs: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING_CONFIRMATION"
    )
    data_version: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SlopeAssetModel(Base):
    __tablename__ = "slope_assets"
    __table_args__ = (
        CheckConstraint(
            "side IN ('LEFT', 'RIGHT', 'BOTH', 'UNKNOWN')",
            name="ck_slope_assets_side",
        ),
        CheckConstraint("end_stake >= start_stake", name="ck_slope_assets_stake_range"),
        CheckConstraint(
            "crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_slope_assets_crs",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_slope_assets_tenant_id_id"),
        UniqueConstraint("tenant_id", "slope_code", name="uq_slope_assets_tenant_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    slope_code: Mapped[str] = mapped_column(String(64), nullable=False)
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    start_stake: Mapped[int] = mapped_column(Integer, nullable=False)
    end_stake: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(32), nullable=False)
    geom_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(
        String(128), nullable=False, default="MANUAL_IMPORT"
    )
    crs: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING_CONFIRMATION"
    )
    data_version: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CoordinateTransformModel(Base):
    __tablename__ = "coordinate_transforms"
    __table_args__ = (
        CheckConstraint(
            "source_crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_coordinate_transforms_source_crs",
        ),
        CheckConstraint(
            "target_crs IN ('WGS84', 'GCJ02', 'CGCS2000', 'PENDING_CONFIRMATION')",
            name="ck_coordinate_transforms_target_crs",
        ),
        CheckConstraint(
            "source_crs != target_crs",
            name="ck_coordinate_transforms_crs_pair",
        ),
        CheckConstraint(
            "method IN ('CONFIG_ONLY', 'AFFINE', 'HELMERT', 'MANUAL_REVIEW')",
            name="ck_coordinate_transforms_method",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DEPRECATED', 'PENDING_CONFIRMATION')",
            name="ck_coordinate_transforms_status",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_crs",
            "target_crs",
            "version",
            name="uq_coordinate_transforms_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    source_crs: Mapped[str] = mapped_column(String(32), nullable=False)
    target_crs: Mapped[str] = mapped_column(String(32), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    params_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RouteModel(Base):
    __tablename__ = "routes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_routes_tenant_id_id"),
        UniqueConstraint("tenant_id", "route_code", name="uq_routes_tenant_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RouteVersionModel(Base):
    __tablename__ = "route_versions"
    __table_args__ = (
        CheckConstraint(
            "route_format IN ('DJI_WPML', 'KML', 'GEOJSON', 'PENDING_CONFIRMATION')",
            name="ck_route_versions_route_format",
        ),
        CheckConstraint(
            "checksum LIKE 'sha256:%'",
            name="ck_route_versions_checksum",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_route_versions_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "route_id",
            "version",
            name="uq_route_versions_tenant_route_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "route_id"],
            ["routes.tenant_id", "routes.id"],
            name="fk_route_versions_tenant_route",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    route_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    route_file_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    route_format: Mapped[str] = mapped_column(String(32), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    path_geom_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    asset_bindings: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    validation_report: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    dji_route_id: Mapped[str | None] = mapped_column(String(128))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MissionModel(Base):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'DISPATCHING', "
            "'DISPATCHED', 'EXECUTING', 'PAUSED', 'RETURNING', 'LOST_LINK', "
            "'COMPLETED', 'ABORTED', 'MEDIA_SYNCING', 'PARTIAL_MEDIA_READY', "
            "'MEDIA_READY', 'ANALYSIS_READY', 'CANCELLED', 'REJECTED', 'EXPIRED', "
            "'DISPATCH_FAILED', 'SYNC_FAILED', 'ARCHIVED')",
            name="ck_missions_status",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_missions_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "route_id"],
            ["routes.tenant_id", "routes.id"],
            name="fk_missions_tenant_route",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "route_version_id"],
            ["route_versions.tenant_id", "route_versions.id"],
            name="fk_missions_tenant_route_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_missions_tenant_device",
        ),
        ForeignKeyConstraint(
            ["dock_id"],
            ["docks.id"],
            name="fk_missions_dock",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    route_id: Mapped[str] = mapped_column(String(64), nullable=False)
    route_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dock_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    schedule_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inspection_targets: Mapped[list] = mapped_column(JSON, nullable=False)
    media_policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
