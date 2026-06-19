from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import re
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
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
EXPECTED_DATABASE_REVISION = "20260618_0001"


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
