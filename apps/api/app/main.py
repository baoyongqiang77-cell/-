from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from queue import Empty
import re
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from drone_inspection.dji_gateway import DjiDock3Simulator, FlightEvent
from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError
from drone_inspection.foundation import TenantContext

from .database import build_session_factory, database_url
from .dependencies import (
    Actor,
    DEMO_TOKENS,
    actor_from_authorization,
    repository,
    request_meta,
    resolve_tenant_context,
)
from .device_registry import (
    DeviceRegistryRepository,
    DeviceRegistryService,
    device_payload,
    dock_payload,
)
from .flight_exceptions import FlightExceptionService
from .gis_assets import (
    GisAssetRepository,
    GisAssetService,
    bridge_asset_payload,
    coordinate_transform_payload,
    road_asset_payload,
    slope_asset_payload,
)
from .mission_management import (
    MissionManagementService,
    MissionRepository,
    mission_payload,
)
from .media_sync import MediaSyncService
from .repositories import RequestMeta, U0Repository
from .route_management import (
    RouteManagementService,
    RouteRepository,
    route_payload,
    route_version_payload,
)
from .telemetry_events import TelemetryEventService
from .telemetry_hub import TelemetryHub, TelemetrySubscription


ERROR_STATUS_CODES = {
    "AUTH_401": 401,
    "PERM_403": 403,
    "TENANT_403": 403,
    "TENANT_404": 404,
    "FEATURE_403": 403,
    "DATA_GRANT_412": 412,
    "IDEMP_409": 409,
    "STATE_409": 409,
    "MISSION_422": 422,
    "DJI_502": 502,
    "GIS_422": 422,
    "MEDIA_415": 415,
    "MEDIA_499": 499,
    "INFER_504": 504,
    "MODEL_412": 412,
    "RUNTIME_428": 428,
}

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
EXPECTED_DATABASE_REVISION = "20260628_0010"


class FeatureEntitlementRequest(BaseModel):
    feature_code: FeatureCode


class DataScopeRequest(BaseModel):
    asset_types: list[str] = Field(default_factory=list)
    sample_ids: list[str] = Field(default_factory=list)


class TenantDataGrantRequest(BaseModel):
    owner_tenant_id: str
    grantee_tenant_id: str
    purpose: list[str]
    data_scope: DataScopeRequest
    effective_from: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.expires_at <= self.effective_from:
            raise ValueError("expires_at must be later than effective_from")
        return self


class DeviceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_type: Literal["DOCK", "DRONE", "PAYLOAD", "EDGE_NODE"]
    name: str = Field(min_length=1)
    manufacturer: str = Field(min_length=1)
    model: str | None = None
    serial_number: str = Field(min_length=1)
    firmware_version: str | None = None


class DeviceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    manufacturer: str | None = Field(default=None, min_length=1)
    model: str | None = None
    firmware_version: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one update field is required")
        for field_name in ("name", "manufacturer"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class DockCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1)
    bound_drone_device_id: str | None = None
    edge_node_device_id: str | None = None
    environment_json: dict = Field(default_factory=dict)


class DockUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bound_drone_device_id: str | None = None
    edge_node_device_id: str | None = None
    environment_json: dict | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one update field is required")
        if "environment_json" in self.model_fields_set and self.environment_json is None:
            raise ValueError("environment_json cannot be null")
        return self


class RoadAssetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_code: str = Field(min_length=1)
    road_name: str = Field(min_length=1)
    direction: Literal["UP", "DOWN", "BIDIRECTIONAL", "RAMP", "UNKNOWN"]
    start_stake: int
    end_stake: int
    geom_json: dict
    source: str = Field(default="MANUAL_IMPORT", min_length=1)
    crs: str = "PENDING_CONFIRMATION"
    data_version: str | None = None


class RoadAssetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_code: str | None = Field(default=None, min_length=1)
    road_name: str | None = Field(default=None, min_length=1)
    direction: Literal["UP", "DOWN", "BIDIRECTIONAL", "RAMP", "UNKNOWN"] | None = None
    start_stake: int | None = None
    end_stake: int | None = None
    geom_json: dict | None = None
    source: str | None = Field(default=None, min_length=1)
    crs: str | None = None
    data_version: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one update field is required")
        if "geom_json" in self.model_fields_set and self.geom_json is None:
            raise ValueError("geom_json cannot be null")
        return self


class BridgeAssetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_code: str = Field(min_length=1)
    bridge_name: str = Field(min_length=1)
    route_code: str = Field(min_length=1)
    stake_no: int
    geom_json: dict
    structure_parts: list = Field(default_factory=list)
    source: str = Field(default="MANUAL_IMPORT", min_length=1)
    crs: str = "PENDING_CONFIRMATION"
    data_version: str | None = None


class BridgeAssetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_code: str | None = Field(default=None, min_length=1)
    bridge_name: str | None = Field(default=None, min_length=1)
    route_code: str | None = Field(default=None, min_length=1)
    stake_no: int | None = None
    geom_json: dict | None = None
    structure_parts: list | None = None
    source: str | None = Field(default=None, min_length=1)
    crs: str | None = None
    data_version: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one update field is required")
        if "geom_json" in self.model_fields_set and self.geom_json is None:
            raise ValueError("geom_json cannot be null")
        return self


class SlopeAssetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slope_code: str = Field(min_length=1)
    route_code: str = Field(min_length=1)
    start_stake: int
    end_stake: int
    side: Literal["LEFT", "RIGHT", "BOTH", "UNKNOWN"]
    geom_json: dict
    source: str = Field(default="MANUAL_IMPORT", min_length=1)
    crs: str = "PENDING_CONFIRMATION"
    data_version: str | None = None


class SlopeAssetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slope_code: str | None = Field(default=None, min_length=1)
    route_code: str | None = Field(default=None, min_length=1)
    start_stake: int | None = None
    end_stake: int | None = None
    side: Literal["LEFT", "RIGHT", "BOTH", "UNKNOWN"] | None = None
    geom_json: dict | None = None
    source: str | None = Field(default=None, min_length=1)
    crs: str | None = None
    data_version: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one update field is required")
        if "geom_json" in self.model_fields_set and self.geom_json is None:
            raise ValueError("geom_json cannot be null")
        return self


class CoordinateTransformCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_crs: str
    target_crs: str
    method: str
    params_json: dict
    version: str = Field(min_length=1)
    status: str


class CoordinateTransformUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_crs: str | None = None
    target_crs: str | None = None
    method: str | None = None
    params_json: dict | None = None
    version: str | None = Field(default=None, min_length=1)
    status: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one update field is required")
        if "params_json" in self.model_fields_set and self.params_json is None:
            raise ValueError("params_json cannot be null")
        return self


class RouteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None


class RouteUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("at least one update field is required")
        return self


class RouteVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    route_file_uri: str = Field(min_length=1)
    route_format: str = Field(min_length=1)
    checksum: str = Field(min_length=1)
    path_geom_json: dict
    asset_bindings: list = Field(default_factory=list)
    validation_report: dict = Field(default_factory=dict)
    dji_route_id: str | None = None
    uploaded_at: datetime | None = None


class MissionTargetRequest(BaseModel):
    asset_type: Literal["road", "bridge", "slope"]
    asset_id: str = Field(min_length=1)


class MissionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str = Field(min_length=1)
    route_version_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    dock_id: str | None = None
    schedule_time: datetime
    inspection_targets: list[MissionTargetRequest]
    media_policy: dict


class MissionApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_system: Literal["BUILT_IN", "OA", "AIRSPACE", "MANUAL"] | None = None
    external_id: str | None = None
    external_status: str | None = None
    callback_payload: dict = Field(default_factory=dict)
    comment: str | None = None


class MissionDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dispatch_note: str | None = None


class TelemetryEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_code: str = Field(min_length=1)
    event_time: datetime
    device_sn: str = Field(min_length=1)
    raw_payload: dict


def create_app(database_url_override: str | None = None) -> FastAPI:
    session_factory = build_session_factory(database_url_override or database_url())

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            try:
                with session_factory.kw["bind"].connect() as connection:
                    revision = connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
            except SQLAlchemyError as exc:
                raise RuntimeError(
                    "database migration is required before API startup"
                ) from exc
            if revision != EXPECTED_DATABASE_REVISION:
                raise RuntimeError(
                    "database migration revision does not match the API"
                )
            yield
        finally:
            session_factory.kw["bind"].dispose()

    app = FastAPI(
        title="无人机智能巡检系统 API",
        version="0.2.0",
        description="U0 API：持久化认证、租户上下文、RBAC、授权、审计和幂等。",
        lifespan=lifespan,
    )
    app.state.session_factory = session_factory
    app.state.telemetry_hub = TelemetryHub()

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Request-Id")
        request.state.request_id = (
            supplied
            if supplied and REQUEST_ID_PATTERN.fullmatch(supplied)
            else f"req_{uuid4().hex[:8]}"
        )
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        exc.request_id = request.state.request_id
        return JSONResponse(
            status_code=ERROR_STATUS_CODES.get(exc.code, 500),
            content=exc.to_response(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        error = DomainError(
            "MISSION_422",
            "请求参数不满足接口要求",
            {"field_errors": _validation_field_errors(exc)},
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=ERROR_STATUS_CODES[error.code],
            content=error.to_response(),
        )

    @app.get("/api/v1/me", tags=["U0 基础平台"])
    def me(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        return {
            "id": actor.id,
            "name": actor.name,
            "roles": list(actor.roles),
            "tenant": _tenant_payload(context),
            "features": _feature_values(context),
        }

    @app.get("/api/v1/tenant-context", tags=["U0 基础平台"])
    def tenant_context(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        return {
            "actor": {
                "id": actor.id,
                "name": actor.name,
                "home_tenant_id": actor.home_tenant_id,
                "roles": list(actor.roles),
            },
            "tenant": _tenant_payload(context),
            "features": _feature_values(context),
            "switchable_tenant_ids": repo.switchable_tenant_ids(actor),
        }

    @app.post(
        "/api/v1/admin/tenants/{tenant_id}/feature-entitlements",
        tags=["U0 基础平台"],
    )
    def configure_feature_entitlement(
        tenant_id: str,
        payload: FeatureEntitlementRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        _require_roles(
            request,
            repo,
            actor,
            {"PLATFORM_ADMIN"},
            meta,
            action="admin_write_denied",
        )
        return repo.enable_feature(
            actor,
            tenant_id,
            payload.feature_code,
            idempotency_key,
            meta,
        )

    @app.post("/api/v1/admin/tenant-data-grants", tags=["U0 基础平台"])
    def register_tenant_data_grant(
        payload: TenantDataGrantRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        _require_roles(
            request,
            repo,
            actor,
            {"PLATFORM_ADMIN"},
            meta,
            action="admin_write_denied",
        )
        return repo.create_data_grant(
            actor=actor,
            owner_tenant_id=payload.owner_tenant_id,
            grantee_tenant_id=payload.grantee_tenant_id,
            purposes=payload.purpose,
            asset_types=payload.data_scope.asset_types,
            sample_ids=payload.data_scope.sample_ids,
            effective_from=payload.effective_from,
            expires_at=payload.expires_at,
            idempotency_key=idempotency_key,
            request_meta=meta,
        )

    @app.get("/api/v1/admin/audit-logs", tags=["U0 基础平台"])
    def audit_logs(
        request: Request,
        tenant_id: str | None = None,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
    ) -> dict:
        _require_roles(
            request,
            repo,
            actor,
            {"PLATFORM_ADMIN", "AUDIT_VIEWER"},
            meta,
            action="admin_audit_query_denied",
        )
        return {
            "items": [_audit_log_payload(log) for log in repo.audit_logs(tenant_id)]
        }

    @app.get("/api/v1/devices", tags=["U1 device registry"])
    def list_devices(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        registry = DeviceRegistryRepository(repo.session)
        return {
            "items": [
                device_payload(item)
                for item in registry.list_devices(context.tenant_id)
            ]
        }

    @app.get("/api/v1/devices/{device_id}", tags=["U1 device registry"])
    def get_device(
        device_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        registry = DeviceRegistryRepository(repo.session)
        try:
            return device_payload(registry.device(context.tenant_id, device_id))
        except DomainError as exc:
            _commit_registry_read_denial(
                request, repo, actor, context, meta, exc, "device", device_id
            )
            raise

    @app.get("/api/v1/docks", tags=["U1 device registry"])
    def list_docks(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        registry = DeviceRegistryRepository(repo.session)
        return {
            "items": [
                dock_payload(item) for item in registry.list_docks(context.tenant_id)
            ]
        }

    @app.get("/api/v1/docks/{dock_id}", tags=["U1 device registry"])
    def get_dock(
        dock_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        registry = DeviceRegistryRepository(repo.session)
        try:
            return dock_payload(registry.dock(context.tenant_id, dock_id))
        except DomainError as exc:
            _commit_registry_read_denial(
                request, repo, actor, context, meta, exc, "dock", dock_id
            )
            raise

    @app.get("/api/v1/gis/road-assets", tags=["U1 GIS assets"])
    def list_road_assets(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        return {
            "items": [
                road_asset_payload(item)
                for item in assets.list_road_assets(context.tenant_id)
            ]
        }

    @app.get("/api/v1/gis/road-assets/{asset_id}", tags=["U1 GIS assets"])
    def get_road_asset(
        asset_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        try:
            return road_asset_payload(assets.road_asset(context.tenant_id, asset_id))
        except DomainError as exc:
            _commit_gis_read_denial(
                request, repo, actor, context, meta, exc, "road_asset", asset_id
            )
            raise

    @app.get("/api/v1/gis/bridge-assets", tags=["U1 GIS assets"])
    def list_bridge_assets(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        return {
            "items": [
                bridge_asset_payload(item)
                for item in assets.list_bridge_assets(context.tenant_id)
            ]
        }

    @app.get("/api/v1/gis/bridge-assets/{asset_id}", tags=["U1 GIS assets"])
    def get_bridge_asset(
        asset_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        try:
            return bridge_asset_payload(assets.bridge_asset(context.tenant_id, asset_id))
        except DomainError as exc:
            _commit_gis_read_denial(
                request, repo, actor, context, meta, exc, "bridge_asset", asset_id
            )
            raise

    @app.get("/api/v1/gis/slope-assets", tags=["U1 GIS assets"])
    def list_slope_assets(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        return {
            "items": [
                slope_asset_payload(item)
                for item in assets.list_slope_assets(context.tenant_id)
            ]
        }

    @app.get("/api/v1/gis/slope-assets/{asset_id}", tags=["U1 GIS assets"])
    def get_slope_asset(
        asset_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        try:
            return slope_asset_payload(assets.slope_asset(context.tenant_id, asset_id))
        except DomainError as exc:
            _commit_gis_read_denial(
                request, repo, actor, context, meta, exc, "slope_asset", asset_id
            )
            raise

    @app.get("/api/v1/gis/coordinate-transforms", tags=["U1 GIS assets"])
    def list_coordinate_transforms(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        return {
            "items": [
                coordinate_transform_payload(item)
                for item in assets.list_coordinate_transforms(context.tenant_id)
            ]
        }

    @app.get(
        "/api/v1/gis/coordinate-transforms/{transform_id}",
        tags=["U1 GIS assets"],
    )
    def get_coordinate_transform(
        transform_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        assets = GisAssetRepository(repo.session)
        try:
            return coordinate_transform_payload(
                assets.coordinate_transform(context.tenant_id, transform_id)
            )
        except DomainError as exc:
            _commit_gis_read_denial(
                request,
                repo,
                actor,
                context,
                meta,
                exc,
                "coordinate_transform",
                transform_id,
            )
            raise

    @app.post("/api/v1/admin/gis/road-assets", tags=["U1 GIS assets"])
    def create_road_asset(
        payload: RoadAssetCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "road_asset",
            None,
            lambda: service.create_road_asset(
                actor.id,
                context.tenant_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.patch("/api/v1/admin/gis/road-assets/{asset_id}", tags=["U1 GIS assets"])
    def update_road_asset(
        asset_id: str,
        payload: RoadAssetUpdateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "road_asset",
            asset_id,
            lambda: service.update_road_asset(
                actor.id,
                context.tenant_id,
                asset_id,
                payload.model_dump(exclude_unset=True),
                idempotency_key,
                meta,
            ),
        )

    @app.post("/api/v1/admin/gis/bridge-assets", tags=["U1 GIS assets"])
    def create_bridge_asset(
        payload: BridgeAssetCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "bridge_asset",
            None,
            lambda: service.create_bridge_asset(
                actor.id,
                context.tenant_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.patch("/api/v1/admin/gis/bridge-assets/{asset_id}", tags=["U1 GIS assets"])
    def update_bridge_asset(
        asset_id: str,
        payload: BridgeAssetUpdateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "bridge_asset",
            asset_id,
            lambda: service.update_bridge_asset(
                actor.id,
                context.tenant_id,
                asset_id,
                payload.model_dump(exclude_unset=True),
                idempotency_key,
                meta,
            ),
        )

    @app.post("/api/v1/admin/gis/slope-assets", tags=["U1 GIS assets"])
    def create_slope_asset(
        payload: SlopeAssetCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "slope_asset",
            None,
            lambda: service.create_slope_asset(
                actor.id,
                context.tenant_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.patch("/api/v1/admin/gis/slope-assets/{asset_id}", tags=["U1 GIS assets"])
    def update_slope_asset(
        asset_id: str,
        payload: SlopeAssetUpdateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "slope_asset",
            asset_id,
            lambda: service.update_slope_asset(
                actor.id,
                context.tenant_id,
                asset_id,
                payload.model_dump(exclude_unset=True),
                idempotency_key,
                meta,
            ),
        )

    @app.post("/api/v1/admin/gis/coordinate-transforms", tags=["U1 GIS assets"])
    def create_coordinate_transform(
        payload: CoordinateTransformCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "coordinate_transform",
            None,
            lambda: service.create_coordinate_transform(
                actor.id,
                context.tenant_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.patch(
        "/api/v1/admin/gis/coordinate-transforms/{transform_id}",
        tags=["U1 GIS assets"],
    )
    def update_coordinate_transform(
        transform_id: str,
        payload: CoordinateTransformUpdateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _gis_write_context(request, repo, actor, x_tenant_id, meta)
        service = GisAssetService(repo.session)
        return _run_gis_write(
            request,
            repo,
            actor,
            context,
            meta,
            "coordinate_transform",
            transform_id,
            lambda: service.update_coordinate_transform(
                actor.id,
                context.tenant_id,
                transform_id,
                payload.model_dump(exclude_unset=True),
                idempotency_key,
                meta,
            ),
        )

    @app.get("/api/v1/routes", tags=["U1 routes"])
    def list_routes(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        routes = RouteRepository(repo.session)
        return {
            "items": [
                route_payload(item) for item in routes.list_routes(context.tenant_id)
            ]
        }

    @app.get("/api/v1/routes/{route_id}", tags=["U1 routes"])
    def get_route(
        route_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        routes = RouteRepository(repo.session)
        try:
            return route_payload(routes.route(context.tenant_id, route_id))
        except DomainError as exc:
            _commit_route_read_denial(
                request, repo, actor, context, meta, exc, "route", route_id
            )
            raise

    @app.get("/api/v1/routes/{route_id}/versions", tags=["U1 routes"])
    def list_route_versions(
        route_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        routes = RouteRepository(repo.session)
        try:
            return {
                "items": [
                    route_version_payload(item)
                    for item in routes.list_versions(context.tenant_id, route_id)
                ]
            }
        except DomainError as exc:
            _commit_route_read_denial(
                request, repo, actor, context, meta, exc, "route", route_id
            )
            raise

    @app.get("/api/v1/routes/{route_id}/versions/{version_id}", tags=["U1 routes"])
    def get_route_version(
        route_id: str,
        version_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        routes = RouteRepository(repo.session)
        try:
            return route_version_payload(
                routes.version(context.tenant_id, route_id, version_id)
            )
        except DomainError as exc:
            _commit_route_read_denial(
                request, repo, actor, context, meta, exc, "route_version", version_id
            )
            raise

    @app.post("/api/v1/admin/routes", tags=["U1 routes"])
    def create_route(
        payload: RouteCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _route_write_context(request, repo, actor, x_tenant_id, meta)
        service = RouteManagementService(repo.session)
        return _run_route_write(
            request,
            repo,
            actor,
            context,
            meta,
            "route",
            None,
            lambda: service.create_route(
                actor.id,
                context.tenant_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.patch("/api/v1/admin/routes/{route_id}", tags=["U1 routes"])
    def update_route(
        route_id: str,
        payload: RouteUpdateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _route_write_context(request, repo, actor, x_tenant_id, meta)
        service = RouteManagementService(repo.session)
        return _run_route_write(
            request,
            repo,
            actor,
            context,
            meta,
            "route",
            route_id,
            lambda: service.update_route(
                actor.id,
                context.tenant_id,
                route_id,
                payload.model_dump(exclude_unset=True),
                idempotency_key,
                meta,
            ),
        )

    @app.post("/api/v1/admin/routes/{route_id}/versions", tags=["U1 routes"])
    def create_route_version(
        route_id: str,
        payload: RouteVersionCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _route_write_context(request, repo, actor, x_tenant_id, meta)
        service = RouteManagementService(repo.session)
        return _run_route_write(
            request,
            repo,
            actor,
            context,
            meta,
            "route_version",
            route_id,
            lambda: service.create_route_version(
                actor.id,
                context.tenant_id,
                route_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.get("/api/v1/missions", tags=["U1 missions"])
    def list_missions(
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        missions = MissionRepository(repo.session)
        return {
            "items": [
                mission_payload(item)
                for item in missions.list_missions(context.tenant_id)
            ]
        }

    @app.get("/api/v1/missions/{mission_id}", tags=["U1 missions"])
    def get_mission(
        mission_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        missions = MissionRepository(repo.session)
        try:
            return mission_payload(missions.mission(context.tenant_id, mission_id))
        except DomainError as exc:
            _commit_mission_read_denial(
                request, repo, actor, context, meta, exc, "mission", mission_id
            )
            raise

    @app.post("/api/v1/missions", tags=["U1 missions"])
    def create_mission(
        payload: MissionCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = MissionManagementService(repo.session)
        return _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "mission",
            None,
            lambda: service.create_mission(
                actor.id,
                context.tenant_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.post("/api/v1/missions/{mission_id}/submit-approval", tags=["U1 missions"])
    def submit_mission_approval(
        mission_id: str,
        payload: MissionApprovalRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = MissionManagementService(repo.session)
        return _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "mission",
            mission_id,
            lambda: service.submit_approval(
                actor.id,
                context.tenant_id,
                mission_id,
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.post(
        "/api/v1/missions/{mission_id}/approvals/{approval_id}/approve",
        tags=["U1 missions"],
    )
    def approve_mission(
        mission_id: str,
        approval_id: str,
        payload: MissionApprovalRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = MissionManagementService(repo.session)
        return _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "mission_approval",
            approval_id,
            lambda: service.decide_approval(
                actor.id,
                context.tenant_id,
                mission_id,
                approval_id,
                "APPROVED",
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.post(
        "/api/v1/missions/{mission_id}/approvals/{approval_id}/reject",
        tags=["U1 missions"],
    )
    def reject_mission(
        mission_id: str,
        approval_id: str,
        payload: MissionApprovalRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = MissionManagementService(repo.session)
        return _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "mission_approval",
            approval_id,
            lambda: service.decide_approval(
                actor.id,
                context.tenant_id,
                mission_id,
                approval_id,
                "REJECTED",
                payload.model_dump(),
                idempotency_key,
                meta,
            ),
        )

    @app.post("/api/v1/missions/{mission_id}/dispatch", tags=["U1 missions"])
    def dispatch_mission(
        mission_id: str,
        payload: MissionDispatchRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = MissionManagementService(repo.session)
        return _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "mission",
            mission_id,
            lambda: service.dispatch_mission(
                actor.id,
                context.tenant_id,
                mission_id,
                payload.model_dump(),
                idempotency_key,
                meta,
                DjiDock3Simulator(),
            ),
        )

    @app.get("/api/v1/missions/{mission_id}/telemetry-events", tags=["U1 missions"])
    def list_telemetry_events(
        mission_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = TelemetryEventService(repo.session)
        try:
            return {"items": service.list_events(context.tenant_id, mission_id)}
        except DomainError as exc:
            _commit_mission_read_denial(
                request, repo, actor, context, meta, exc, "mission", mission_id
            )
            raise

    @app.post("/api/v1/missions/{mission_id}/telemetry-events", tags=["U1 missions"])
    def record_telemetry_event(
        mission_id: str,
        payload: TelemetryEventRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = TelemetryEventService(repo.session)
        event = FlightEvent(
            event_code=payload.event_code,
            event_time=payload.event_time,
            device_sn=payload.device_sn,
            raw_payload=payload.raw_payload,
        )
        result = _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "mission",
            mission_id,
            lambda: service.record_event(
                actor.id,
                context.tenant_id,
                mission_id,
                event,
                idempotency_key,
                meta,
            ),
        )
        request.app.state.telemetry_hub.broadcast(
            context.tenant_id,
            mission_id,
            {"type": "event", "mission_id": mission_id, "item": result},
        )
        return result

    @app.websocket("/api/v1/missions/{mission_id}/telemetry/ws")
    async def mission_telemetry_ws(websocket: WebSocket, mission_id: str) -> None:
        await websocket.accept()
        request_id = f"req_{uuid4().hex[:8]}"
        meta = RequestMeta(request_id, websocket.client.host if websocket.client else None)
        session_factory = websocket.app.state.session_factory
        hub: TelemetryHub = websocket.app.state.telemetry_hub
        subscription: TelemetrySubscription | None = None
        with session_factory() as session:
            repo = U0Repository(session)
            try:
                actor = _actor_from_websocket(websocket, repo)
                context = resolve_tenant_context(
                    repo,
                    actor,
                    websocket.headers.get("X-Tenant-Id"),
                )
                if not context.has_feature(FeatureCode.FLIGHT_CONTROL):
                    raise DomainError(
                        "FEATURE_403",
                        "Tenant is not entitled to the requested feature",
                        {"feature_code": FeatureCode.FLIGHT_CONTROL.value},
                    )
                service = TelemetryEventService(session)
                service.list_events(context.tenant_id, mission_id)
                subscription = hub.subscribe(context.tenant_id, mission_id)
                items = service.list_events(context.tenant_id, mission_id)
            except DomainError as exc:
                await websocket.send_json(
                    {
                        "code": exc.code,
                        "message": exc.message,
                        "request_id": request_id,
                        "details": exc.details,
                    }
                )
                await websocket.close()
                return
        await websocket.send_json(
            {"type": "snapshot", "mission_id": mission_id, "items": items}
        )
        try:
            await _forward_telemetry(subscription, websocket)
        finally:
            hub.unsubscribe(subscription)

    @app.get("/api/v1/missions/{mission_id}/flight-exceptions", tags=["U1 missions"])
    def list_flight_exceptions(
        mission_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = FlightExceptionService(repo.session)
        try:
            return {"items": service.list_exceptions(context.tenant_id, mission_id)}
        except DomainError as exc:
            _commit_mission_read_denial(
                request, repo, actor, context, meta, exc, "mission", mission_id
            )
            raise

    @app.post(
        "/api/v1/missions/{mission_id}/flight-events/{flight_event_id}/link-exception",
        tags=["U1 missions"],
    )
    def link_flight_exception(
        mission_id: str,
        flight_event_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = FlightExceptionService(repo.session)
        return _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "flight_exception",
            flight_event_id,
            lambda: service.link_exception(
                actor.id,
                context.tenant_id,
                mission_id,
                flight_event_id,
                idempotency_key,
                meta,
            ),
        )

    @app.get("/api/v1/missions/{mission_id}/media-files", tags=["U1 missions"])
    def list_mission_media_files(
        mission_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = MediaSyncService(repo.session)
        try:
            return {"items": service.list_media_files(context.tenant_id, mission_id)}
        except DomainError as exc:
            _commit_mission_read_denial(
                request, repo, actor, context, meta, exc, "mission", mission_id
            )
            raise

    @app.post(
        "/api/v1/missions/{mission_id}/flight-events/{flight_event_id}/sync-media",
        tags=["U1 missions"],
    )
    def sync_mission_media_file(
        mission_id: str,
        flight_event_id: str,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _resolve_context(request, repo, actor, x_tenant_id, meta)
        _require_feature(request, repo, actor, context, FeatureCode.FLIGHT_CONTROL, meta)
        service = MediaSyncService(repo.session)
        return _run_mission_write(
            request,
            repo,
            actor,
            context,
            meta,
            "media_file",
            flight_event_id,
            lambda: service.sync_media(
                actor.id,
                context.tenant_id,
                mission_id,
                flight_event_id,
                idempotency_key,
                meta,
            ),
        )

    @app.post("/api/v1/admin/devices", tags=["U1 device registry"])
    def create_device(
        payload: DeviceCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _registry_write_context(
            request, repo, actor, x_tenant_id, meta
        )
        service = DeviceRegistryService(repo.session)
        return _run_registry_write(
            request,
            repo,
            actor,
            context,
            meta,
            "device",
            None,
            lambda: service.create_device(
                actor_id=actor.id,
                tenant_id=context.tenant_id,
                values=payload.model_dump(),
                idempotency_key=idempotency_key,
                request_meta=meta,
            ),
        )

    @app.patch("/api/v1/admin/devices/{device_id}", tags=["U1 device registry"])
    def update_device(
        device_id: str,
        payload: DeviceUpdateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _registry_write_context(
            request, repo, actor, x_tenant_id, meta
        )
        service = DeviceRegistryService(repo.session)
        return _run_registry_write(
            request,
            repo,
            actor,
            context,
            meta,
            "device",
            device_id,
            lambda: service.update_device(
                actor_id=actor.id,
                tenant_id=context.tenant_id,
                device_id=device_id,
                values=payload.model_dump(exclude_unset=True),
                idempotency_key=idempotency_key,
                request_meta=meta,
            ),
        )

    @app.post("/api/v1/admin/docks", tags=["U1 device registry"])
    def create_dock(
        payload: DockCreateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _registry_write_context(
            request, repo, actor, x_tenant_id, meta
        )
        service = DeviceRegistryService(repo.session)
        return _run_registry_write(
            request,
            repo,
            actor,
            context,
            meta,
            "dock",
            None,
            lambda: service.create_dock(
                actor_id=actor.id,
                tenant_id=context.tenant_id,
                values=payload.model_dump(),
                idempotency_key=idempotency_key,
                request_meta=meta,
            ),
        )

    @app.patch("/api/v1/admin/docks/{dock_id}", tags=["U1 device registry"])
    def update_dock(
        dock_id: str,
        payload: DockUpdateRequest,
        request: Request,
        actor: Actor = Depends(actor_from_authorization),
        repo: U0Repository = Depends(repository),
        meta: RequestMeta = Depends(request_meta),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        context = _registry_write_context(
            request, repo, actor, x_tenant_id, meta
        )
        service = DeviceRegistryService(repo.session)
        return _run_registry_write(
            request,
            repo,
            actor,
            context,
            meta,
            "dock",
            dock_id,
            lambda: service.update_dock(
                actor_id=actor.id,
                tenant_id=context.tenant_id,
                dock_id=dock_id,
                values=payload.model_dump(exclude_unset=True),
                idempotency_key=idempotency_key,
                request_meta=meta,
            ),
        )

    return app


def _resolve_context(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    target_tenant_id: str | None,
    meta: RequestMeta,
) -> TenantContext:
    try:
        return resolve_tenant_context(repo, actor, target_tenant_id)
    except DomainError as exc:
        if exc.code == "TENANT_403":
            repo.session.rollback()
            exc.request_id = meta.request_id
            U0Repository.commit_denial_audit(
                request.app.state.session_factory,
                tenant_id=actor.home_tenant_id,
                actor=actor.id,
                action="tenant_switch_denied",
                resource_type="tenant",
                resource_id=target_tenant_id,
                request_meta=meta,
                code=exc.code,
            )
        raise


async def _forward_telemetry(
    subscription: TelemetrySubscription,
    websocket: WebSocket,
) -> None:
    while True:
        try:
            message = await asyncio.to_thread(subscription.queue.get, True, 0.1)
            await websocket.send_json(message)
        except Empty:
            continue
        except asyncio.CancelledError:
            return
        except RuntimeError:
            return


def _actor_from_websocket(websocket: WebSocket, repo: U0Repository) -> Actor:
    authorization = websocket.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise DomainError("AUTH_401", "Missing or expired token")
    token = authorization.removeprefix("Bearer ").strip()
    user_id = DEMO_TOKENS.get(token)
    if user_id is None:
        raise DomainError("AUTH_401", "Missing or expired token")
    return repo.home_actor(user_id)


def _require_roles(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    allowed: set[str],
    meta: RequestMeta,
    action: str,
) -> None:
    try:
        repo.require_role(actor, allowed)
    except DomainError as exc:
        repo.session.rollback()
        exc.request_id = meta.request_id
        U0Repository.commit_denial_audit(
            request.app.state.session_factory,
            tenant_id=actor.home_tenant_id,
            actor=actor.id,
            action=action,
            resource_type="admin_api",
            request_meta=meta,
            code=exc.code,
        )
        raise


def _require_feature(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    feature: FeatureCode,
    meta: RequestMeta,
) -> None:
    if context.has_feature(feature):
        return
    error = DomainError(
        "FEATURE_403",
        "当前租户未开通目标功能",
        {"feature_code": feature.value},
    )
    repo.session.rollback()
    error.request_id = meta.request_id
    U0Repository.commit_denial_audit(
        request.app.state.session_factory,
        tenant_id=context.tenant_id,
        actor=actor.id,
        action="feature_denied",
        resource_type="feature",
        resource_id=feature.value,
        request_meta=meta,
        code=error.code,
    )
    raise error


def _commit_registry_read_denial(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    error: DomainError,
    resource_type: str,
    resource_id: str,
) -> None:
    if error.code != "TENANT_404":
        return
    repo.session.rollback()
    error.request_id = meta.request_id
    U0Repository.commit_denial_audit(
        request.app.state.session_factory,
        tenant_id=context.tenant_id,
        actor=actor.id,
        action="registry_read_denied",
        resource_type=resource_type,
        resource_id=resource_id,
        request_meta=meta,
        code=error.code,
    )


def _commit_gis_read_denial(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    error: DomainError,
    resource_type: str,
    resource_id: str,
) -> None:
    if error.code != "TENANT_404":
        return
    repo.session.rollback()
    error.request_id = meta.request_id
    U0Repository.commit_denial_audit(
        request.app.state.session_factory,
        tenant_id=context.tenant_id,
        actor=actor.id,
        action="gis_asset_read_denied",
        resource_type=resource_type,
        resource_id=resource_id,
        request_meta=meta,
        code=error.code,
    )


def _commit_route_read_denial(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    error: DomainError,
    resource_type: str,
    resource_id: str,
) -> None:
    if error.code != "TENANT_404":
        return
    repo.session.rollback()
    error.request_id = meta.request_id
    U0Repository.commit_denial_audit(
        request.app.state.session_factory,
        tenant_id=context.tenant_id,
        actor=actor.id,
        action="route_read_denied",
        resource_type=resource_type,
        resource_id=resource_id,
        request_meta=meta,
        code=error.code,
    )


def _commit_mission_read_denial(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    error: DomainError,
    resource_type: str,
    resource_id: str,
) -> None:
    if error.code != "TENANT_404":
        return
    repo.session.rollback()
    error.request_id = meta.request_id
    U0Repository.commit_denial_audit(
        request.app.state.session_factory,
        tenant_id=context.tenant_id,
        actor=actor.id,
        action="mission_read_denied",
        resource_type=resource_type,
        resource_id=resource_id,
        request_meta=meta,
        code=error.code,
    )


def _registry_write_context(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    target_tenant_id: str | None,
    meta: RequestMeta,
) -> TenantContext:
    context = _resolve_context(request, repo, actor, target_tenant_id, meta)
    _require_roles(
        request,
        repo,
        actor,
        {"PLATFORM_ADMIN"},
        meta,
        action="registry_write_denied",
    )
    _require_feature(
        request,
        repo,
        actor,
        context,
        FeatureCode.FLIGHT_CONTROL,
        meta,
    )
    return context


def _gis_write_context(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    target_tenant_id: str | None,
    meta: RequestMeta,
) -> TenantContext:
    context = _resolve_context(request, repo, actor, target_tenant_id, meta)
    _require_roles(
        request,
        repo,
        actor,
        {"PLATFORM_ADMIN"},
        meta,
        action="gis_asset_write_denied",
    )
    _require_feature(
        request,
        repo,
        actor,
        context,
        FeatureCode.FLIGHT_CONTROL,
        meta,
    )
    return context


def _route_write_context(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    target_tenant_id: str | None,
    meta: RequestMeta,
) -> TenantContext:
    context = _resolve_context(request, repo, actor, target_tenant_id, meta)
    _require_roles(
        request,
        repo,
        actor,
        {"PLATFORM_ADMIN"},
        meta,
        action="route_write_denied",
    )
    _require_feature(
        request,
        repo,
        actor,
        context,
        FeatureCode.FLIGHT_CONTROL,
        meta,
    )
    return context


def _run_registry_write(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    resource_type: str,
    resource_id: str | None,
    operation: Callable[[], dict],
) -> dict:
    try:
        return operation()
    except DomainError as exc:
        if exc.code not in {"IDEMP_409", "MISSION_422", "TENANT_404"}:
            raise
        repo.session.rollback()
        exc.request_id = meta.request_id
        U0Repository.commit_denial_audit(
            request.app.state.session_factory,
            tenant_id=context.tenant_id,
            actor=actor.id,
            action="registry_write_denied",
            resource_type=resource_type,
            resource_id=resource_id,
            request_meta=meta,
            code=exc.code,
        )
        raise


def _run_gis_write(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    resource_type: str,
    resource_id: str | None,
    operation: Callable[[], dict],
) -> dict:
    try:
        return operation()
    except DomainError as exc:
        if exc.code not in {
            "IDEMP_409",
            "MISSION_422",
            "GIS_422",
            "TENANT_404",
            "STATE_409",
            "DJI_502",
        }:
            raise
        repo.session.rollback()
        exc.request_id = meta.request_id
        U0Repository.commit_denial_audit(
            request.app.state.session_factory,
            tenant_id=context.tenant_id,
            actor=actor.id,
            action="gis_asset_write_denied",
            resource_type=resource_type,
            resource_id=resource_id,
            request_meta=meta,
            code=exc.code,
        )
        raise


def _run_route_write(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    resource_type: str,
    resource_id: str | None,
    operation: Callable[[], dict],
) -> dict:
    try:
        return operation()
    except DomainError as exc:
        if exc.code not in {"IDEMP_409", "MISSION_422", "GIS_422", "TENANT_404"}:
            raise
        repo.session.rollback()
        exc.request_id = meta.request_id
        U0Repository.commit_denial_audit(
            request.app.state.session_factory,
            tenant_id=context.tenant_id,
            actor=actor.id,
            action="route_write_denied",
            resource_type=resource_type,
            resource_id=resource_id,
            request_meta=meta,
            code=exc.code,
        )
        raise


def _run_mission_write(
    request: Request,
    repo: U0Repository,
    actor: Actor,
    context: TenantContext,
    meta: RequestMeta,
    resource_type: str,
    resource_id: str | None,
    operation: Callable[[], dict],
) -> dict:
    try:
        return operation()
    except DomainError as exc:
        if exc.code not in {"IDEMP_409", "MISSION_422", "GIS_422", "TENANT_404"}:
            raise
        repo.session.rollback()
        exc.request_id = meta.request_id
        U0Repository.commit_denial_audit(
            request.app.state.session_factory,
            tenant_id=context.tenant_id,
            actor=actor.id,
            action="mission_write_denied",
            resource_type=resource_type,
            resource_id=resource_id,
            request_meta=meta,
            code=exc.code,
        )
        raise


def _tenant_payload(context: TenantContext) -> dict:
    return {
        "id": context.tenant.id,
        "name": context.tenant.name,
        "tenant_type": context.tenant.tenant_type,
        "status": context.tenant.status,
    }


def _feature_values(context: TenantContext) -> list[str]:
    return sorted(feature.value for feature in context.features)


def _validation_field_errors(exc: RequestValidationError) -> list[dict]:
    return [
        {
            "loc": [str(part) for part in item.get("loc", [])],
            "message": item.get("msg", "参数错误"),
            "type": item.get("type", "value_error"),
        }
        for item in exc.errors()
    ]


def _audit_log_payload(log) -> dict:
    return {
        "tenant_id": log.tenant_id,
        "actor": log.actor,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "client_ip": log.client_ip,
        "request_id": log.request_id,
        "code": log.code,
        "before_status": log.before_status,
        "after_status": log.after_status,
        "created_at": log.created_at.isoformat(),
    }


app = create_app()
