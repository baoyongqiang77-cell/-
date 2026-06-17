from __future__ import annotations

from json import dumps

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError
from drone_inspection.foundation import DataGrant, PlatformState, TenantContext

from .dependencies import Actor, actor_from_authorization, platform_state, resolve_tenant_context


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


class FeatureEntitlementRequest(BaseModel):
    feature_code: FeatureCode


class DataScopeRequest(BaseModel):
    sample_ids: list[str] = Field(default_factory=list)


class TenantDataGrantRequest(BaseModel):
    owner_tenant_id: str
    grantee_tenant_id: str
    purpose: list[str]
    data_scope: DataScopeRequest


def create_app() -> FastAPI:
    app = FastAPI(
        title="无人机智能巡检系统 API",
        version="0.1.0",
        description="U0 正式 API 骨架：认证、租户上下文、功能授权和统一错误响应。",
    )
    app.state.platform_state = PlatformState.bootstrap()

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
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
        )
        return JSONResponse(
            status_code=ERROR_STATUS_CODES[error.code],
            content=error.to_response(),
        )

    @app.get("/api/v1/me", tags=["U0 基础平台"])
    def me(
        actor: Actor = Depends(actor_from_authorization),
        state: PlatformState = Depends(platform_state),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = resolve_tenant_context(state, actor, x_tenant_id)
        return {
            "id": actor.id,
            "name": actor.name,
            "roles": list(actor.roles),
            "tenant": _tenant_payload(context),
            "features": _feature_values(context),
        }

    @app.get("/api/v1/tenant-context", tags=["U0 基础平台"])
    def tenant_context(
        actor: Actor = Depends(actor_from_authorization),
        state: PlatformState = Depends(platform_state),
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ) -> dict:
        context = resolve_tenant_context(state, actor, x_tenant_id)
        home_context = state.tenant_context(actor.home_tenant_id)
        switchable_tenant_ids = (
            sorted(state.tenants)
            if home_context.tenant_type == "PLATFORM_OPERATOR"
            else [actor.home_tenant_id]
        )
        return {
            "actor": {
                "id": actor.id,
                "name": actor.name,
                "home_tenant_id": actor.home_tenant_id,
                "roles": list(actor.roles),
            },
            "tenant": _tenant_payload(context),
            "features": _feature_values(context),
            "switchable_tenant_ids": switchable_tenant_ids,
        }

    @app.post(
        "/api/v1/admin/tenants/{tenant_id}/feature-entitlements",
        tags=["U0 基础平台"],
    )
    def configure_feature_entitlement(
        tenant_id: str,
        payload: FeatureEntitlementRequest,
        actor: Actor = Depends(actor_from_authorization),
        state: PlatformState = Depends(platform_state),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        _require_platform_operator(state, actor)
        state.tenant_context(tenant_id)
        response = {
            "tenant_id": tenant_id,
            "feature_code": payload.feature_code.value,
            "enabled": True,
        }
        replay = _record_idempotent(
            state,
            idempotency_key,
            {
                "action": "feature_entitlement",
                "tenant_id": tenant_id,
                "feature_code": payload.feature_code.value,
            },
            response,
        )
        if replay["is_replay"]:
            return replay["response"]
        state.enable_feature(tenant_id, payload.feature_code)
        state.audit(
            tenant_id=tenant_id,
            actor=actor.id,
            action="feature_entitlement_enabled",
            resource_type="feature",
            resource_id=payload.feature_code.value,
        )
        return response

    @app.post("/api/v1/admin/tenant-data-grants", tags=["U0 基础平台"])
    def register_tenant_data_grant(
        payload: TenantDataGrantRequest,
        actor: Actor = Depends(actor_from_authorization),
        state: PlatformState = Depends(platform_state),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        _require_platform_operator(state, actor)
        state.tenant_context(payload.owner_tenant_id)
        state.tenant_context(payload.grantee_tenant_id)
        response = {
            "owner_tenant_id": payload.owner_tenant_id,
            "grantee_tenant_id": payload.grantee_tenant_id,
            "purpose": sorted(payload.purpose),
            "sample_ids": sorted(payload.data_scope.sample_ids),
            "status": "ACTIVE",
        }
        replay = _record_idempotent(
            state,
            idempotency_key,
            {
                "action": "tenant_data_grant",
                "owner_tenant_id": payload.owner_tenant_id,
                "grantee_tenant_id": payload.grantee_tenant_id,
                "purpose": sorted(payload.purpose),
                "sample_ids": sorted(payload.data_scope.sample_ids),
            },
            response,
        )
        if replay["is_replay"]:
            return replay["response"]
        grant = state.add_data_grant(
            owner_tenant_id=payload.owner_tenant_id,
            grantee_tenant_id=payload.grantee_tenant_id,
            purposes=payload.purpose,
            sample_ids=payload.data_scope.sample_ids,
        )
        state.audit(
            tenant_id=grant.grantee_tenant_id,
            actor=actor.id,
            action="tenant_data_grant_created",
            resource_type="tenant_data_grants",
            resource_id=grant.owner_tenant_id,
        )
        return _data_grant_payload(grant)

    @app.get("/api/v1/admin/audit-logs", tags=["U0 基础平台"])
    def audit_logs(
        tenant_id: str | None = None,
        actor: Actor = Depends(actor_from_authorization),
        state: PlatformState = Depends(platform_state),
    ) -> dict:
        _require_platform_operator(state, actor)
        logs = state.audit_logs
        if tenant_id is not None:
            logs = [log for log in logs if log.tenant_id == tenant_id]
        return {"items": [_audit_log_payload(log) for log in logs]}

    return app


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
    errors = []
    for item in exc.errors():
        errors.append(
            {
                "loc": [str(part) for part in item.get("loc", [])],
                "message": item.get("msg", "参数错误"),
                "type": item.get("type", "value_error"),
            }
        )
    return errors


def _require_platform_operator(state: PlatformState, actor: Actor) -> None:
    context = state.tenant_context(actor.home_tenant_id)
    if context.tenant_type == "PLATFORM_OPERATOR":
        return
    state.audit(
        tenant_id=actor.home_tenant_id,
        actor=actor.id,
        action="admin_write_denied",
        resource_type="admin_api",
        code="PERM_403",
    )
    raise DomainError(
        "PERM_403",
        "权限不足",
        {"required_tenant_type": "PLATFORM_OPERATOR"},
    )


def _record_idempotent(
    state: PlatformState,
    idempotency_key: str | None,
    fingerprint_parts: dict,
    response: dict,
) -> dict:
    if not idempotency_key:
        raise DomainError(
            "IDEMP_409",
            "缺少幂等键",
            {"required_header": "Idempotency-Key"},
        )
    fingerprint = dumps(fingerprint_parts, ensure_ascii=False, sort_keys=True)
    recorded = state.idempotency.record(idempotency_key, fingerprint, response)
    return {
        "response": recorded,
        "is_replay": recorded is not response,
    }


def _data_grant_payload(grant: DataGrant) -> dict:
    return {
        "owner_tenant_id": grant.owner_tenant_id,
        "grantee_tenant_id": grant.grantee_tenant_id,
        "purpose": sorted(grant.purposes),
        "sample_ids": sorted(grant.sample_ids),
        "status": grant.status,
    }


def _audit_log_payload(log) -> dict:
    return {
        "tenant_id": log.tenant_id,
        "actor": log.actor,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "code": log.code,
        "before_status": log.before_status,
        "after_status": log.after_status,
    }


app = create_app()
