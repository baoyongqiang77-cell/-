from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError
from drone_inspection.foundation import Tenant, TenantContext

from .models import (
    TenantFeatureEntitlementModel,
    TenantModel,
    UserModel,
    UserTenantRoleModel,
)


@dataclass(frozen=True)
class PersistedActor:
    id: str
    name: str
    home_tenant_id: str
    roles: tuple[str, ...]


class U0Repository:
    def __init__(self, session: Session):
        self.session = session

    def actor(self, user_id: str, tenant_id: str) -> PersistedActor:
        user = self.session.get(UserModel, user_id)
        if user is None or user.status != "ACTIVE":
            raise DomainError("AUTH_401", "未认证或 Token 过期")
        roles = tuple(
            self.session.scalars(
                select(UserTenantRoleModel.role_code)
                .where(
                    UserTenantRoleModel.user_id == user_id,
                    UserTenantRoleModel.tenant_id == tenant_id,
                )
                .order_by(UserTenantRoleModel.role_code)
            ).all()
        )
        return PersistedActor(
            id=user.id,
            name=user.name,
            home_tenant_id=user.home_tenant_id,
            roles=roles,
        )

    def tenant_context(self, tenant_id: str) -> TenantContext:
        tenant = self.session.get(TenantModel, tenant_id)
        if tenant is None:
            raise DomainError("TENANT_404", "租户不存在", {"tenant_id": tenant_id})
        feature_values = self.session.scalars(
            select(TenantFeatureEntitlementModel.feature_code).where(
                TenantFeatureEntitlementModel.tenant_id == tenant_id
            )
        ).all()
        return TenantContext(
            tenant=Tenant(
                id=tenant.id,
                name=tenant.name,
                tenant_type=tenant.tenant_type,
                status=tenant.status,
            ),
            features={FeatureCode(value) for value in feature_values},
        )

    def switchable_tenant_ids(self, actor: PersistedActor) -> list[str]:
        home = self.tenant_context(actor.home_tenant_id)
        allowed_roles = {"PLATFORM_ADMIN", "PLATFORM_OPS"}
        if home.tenant_type != "PLATFORM_OPERATOR" or not allowed_roles.intersection(
            actor.roles
        ):
            return [actor.home_tenant_id]
        return list(self.session.scalars(select(TenantModel.id).order_by(TenantModel.id)))

    def require_role(self, actor: PersistedActor, allowed: set[str]) -> None:
        if allowed.intersection(actor.roles):
            return
        raise DomainError(
            "PERM_403",
            "权限不足",
            {"required_roles": sorted(allowed)},
        )
