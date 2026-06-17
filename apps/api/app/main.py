from __future__ import annotations

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from drone_inspection.errors import DomainError
from drone_inspection.foundation import PlatformState, TenantContext

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


app = create_app()
