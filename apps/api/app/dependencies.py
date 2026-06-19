from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError
from drone_inspection.foundation import TenantContext

from .database import session_dependency
from .repositories import PersistedActor, RequestMeta, U0Repository


DEMO_TOKENS: dict[str, str] = {
    "demo-platform": "u_platform_admin",
    "demo-customer-a": "u_customer_a_operator",
    "demo-customer-b": "u_customer_b_operator",
}


Actor = PersistedActor


def repository(
    session: Session = Depends(session_dependency),
) -> U0Repository:
    return U0Repository(session)


def request_meta(request: Request) -> RequestMeta:
    client_ip = request.client.host if request.client is not None else None
    return RequestMeta(request.state.request_id, client_ip)


def actor_from_authorization(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    repo: U0Repository = Depends(repository),
) -> Actor:
    if not authorization or not authorization.startswith("Bearer "):
        raise DomainError("AUTH_401", "未认证或 Token 过期")
    token = authorization.removeprefix("Bearer ").strip()
    user_id = DEMO_TOKENS.get(token)
    if user_id is None:
        raise DomainError("AUTH_401", "未认证或 Token 过期")
    return repo.home_actor(user_id)


def resolve_tenant_context(
    repo: U0Repository,
    actor: Actor,
    x_tenant_id: str | None,
) -> TenantContext:
    target_tenant_id = x_tenant_id or actor.home_tenant_id
    allowed_roles = {"PLATFORM_ADMIN", "PLATFORM_OPS"}
    home_context = repo.tenant_context(actor.home_tenant_id)
    if target_tenant_id != actor.home_tenant_id and (
        home_context.tenant_type != "PLATFORM_OPERATOR"
        or not allowed_roles.intersection(actor.roles)
    ):
        raise DomainError(
            "TENANT_403",
            "当前用户无目标租户访问权",
            {"target_tenant_id": target_tenant_id},
        )
    return repo.tenant_context(target_tenant_id)
