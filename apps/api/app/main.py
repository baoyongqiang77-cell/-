from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
import re
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError
from drone_inspection.foundation import TenantContext

from .database import build_session_factory, database_url
from .dependencies import (
    Actor,
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
from .gis_assets import (
    GisAssetRepository,
    bridge_asset_payload,
    coordinate_transform_payload,
    road_asset_payload,
    slope_asset_payload,
)
from .repositories import RequestMeta, U0Repository


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
EXPECTED_DATABASE_REVISION = "20260627_0003"


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
