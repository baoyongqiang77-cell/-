from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, Request

from drone_inspection.errors import DomainError
from drone_inspection.foundation import PlatformState, TenantContext


@dataclass(frozen=True)
class Actor:
    id: str
    name: str
    home_tenant_id: str
    roles: tuple[str, ...]


DEMO_TOKENS: dict[str, Actor] = {
    "demo-platform": Actor(
        id="u_platform_admin",
        name="平台管理员",
        home_tenant_id="t_jxjtsz_platform",
        roles=("平台管理员",),
    ),
    "demo-customer-a": Actor(
        id="u_customer_a_operator",
        name="分中心A飞控操作员",
        home_tenant_id="t_customer_001",
        roles=("飞控操作员", "分析查看员"),
    ),
    "demo-customer-b": Actor(
        id="u_customer_b_operator",
        name="分中心B飞控操作员",
        home_tenant_id="t_customer_002",
        roles=("飞控操作员", "分析查看员"),
    ),
}


def platform_state(request: Request) -> PlatformState:
    return request.app.state.platform_state


def actor_from_authorization(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Actor:
    if not authorization or not authorization.startswith("Bearer "):
        raise DomainError("AUTH_401", "未认证或 Token 过期")
    token = authorization.removeprefix("Bearer ").strip()
    actor = DEMO_TOKENS.get(token)
    if actor is None:
        raise DomainError("AUTH_401", "未认证或 Token 过期")
    return actor


def resolve_tenant_context(
    state: PlatformState,
    actor: Actor,
    x_tenant_id: str | None,
) -> TenantContext:
    home_context = state.tenant_context(actor.home_tenant_id)
    target_tenant_id = x_tenant_id or actor.home_tenant_id
    if target_tenant_id != actor.home_tenant_id and home_context.tenant_type != "PLATFORM_OPERATOR":
        state.audit(
            tenant_id=actor.home_tenant_id,
            actor=actor.id,
            action="tenant_switch_denied",
            resource_type="tenant",
            resource_id=target_tenant_id,
            code="TENANT_403",
        )
        raise DomainError(
            "TENANT_403",
            "当前用户无目标租户访问权",
            {"target_tenant_id": target_tenant_id},
        )
    return state.tenant_context(target_tenant_id)
