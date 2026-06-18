from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError
from drone_inspection.foundation import Tenant, TenantContext

from .models import (
    AuditLogModel,
    IdempotencyRecordModel,
    TenantDataGrantModel,
    TenantFeatureEntitlementModel,
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


@dataclass(frozen=True)
class RequestMeta:
    request_id: str
    client_ip: str | None


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

    def run_idempotent(
        self,
        tenant_id: str,
        http_method: str,
        route_id: str,
        key: str | None,
        fingerprint: str,
        operation: Callable[[], dict],
    ) -> dict:
        if not key:
            raise DomainError(
                "IDEMP_409",
                "缺少幂等键",
                {"required_header": "Idempotency-Key"},
            )
        scope = (
            IdempotencyRecordModel.tenant_id == tenant_id,
            IdempotencyRecordModel.http_method == http_method.upper(),
            IdempotencyRecordModel.route_id == route_id,
            IdempotencyRecordModel.idempotency_key == key,
        )
        existing = self.session.scalar(select(IdempotencyRecordModel).where(*scope))
        if existing is not None:
            return self._replay_idempotent(existing, fingerprint)

        response = operation()
        self.session.add(
            IdempotencyRecordModel(
                tenant_id=tenant_id,
                http_method=http_method.upper(),
                route_id=route_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                response=response,
            )
        )
        try:
            self.session.commit()
            return response
        except IntegrityError:
            self.session.rollback()
            winner = self.session.scalar(select(IdempotencyRecordModel).where(*scope))
            if winner is None:
                raise
            return self._replay_idempotent(winner, fingerprint)

    @staticmethod
    def _replay_idempotent(
        record: IdempotencyRecordModel,
        fingerprint: str,
    ) -> dict:
        if record.request_fingerprint != fingerprint:
            raise DomainError(
                "IDEMP_409",
                "幂等键冲突",
                {"idempotency_key": record.idempotency_key},
            )
        return record.response

    def enable_feature(
        self,
        actor: PersistedActor,
        tenant_id: str,
        feature_code: FeatureCode,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.require_role(actor, {"PLATFORM_ADMIN"})
        self.tenant_context(tenant_id)
        fingerprint = self._fingerprint(
            {
                "action": "feature_entitlement",
                "tenant_id": tenant_id,
                "feature_code": feature_code.value,
            }
        )

        def operation() -> dict:
            existing = self.session.scalar(
                select(TenantFeatureEntitlementModel.id).where(
                    TenantFeatureEntitlementModel.tenant_id == tenant_id,
                    TenantFeatureEntitlementModel.feature_code == feature_code.value,
                )
            )
            if existing is None:
                self.session.add(
                    TenantFeatureEntitlementModel(
                        tenant_id=tenant_id,
                        feature_code=feature_code.value,
                    )
                )
            self.audit(
                tenant_id=tenant_id,
                actor=actor.id,
                action="feature_entitlement_enabled",
                resource_type="feature",
                resource_id=feature_code.value,
                request_meta=request_meta,
            )
            return {
                "tenant_id": tenant_id,
                "feature_code": feature_code.value,
                "enabled": True,
            }

        return self.run_idempotent(
            actor.home_tenant_id,
            "POST",
            "feature-entitlement",
            idempotency_key,
            fingerprint,
            operation,
        )

    def audit(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        resource_type: str,
        request_meta: RequestMeta,
        resource_id: str | None = None,
        code: str | None = None,
        before_status: str | None = None,
        after_status: str | None = None,
    ) -> AuditLogModel:
        record = AuditLogModel(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            client_ip=request_meta.client_ip,
            request_id=request_meta.request_id,
            code=code,
            before_status=before_status,
            after_status=after_status,
        )
        self.session.add(record)
        return record

    def create_data_grant(
        self,
        actor: PersistedActor,
        owner_tenant_id: str,
        grantee_tenant_id: str,
        purposes: list[str],
        asset_types: list[str],
        sample_ids: list[str],
        effective_from: datetime,
        expires_at: datetime,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.require_role(actor, {"PLATFORM_ADMIN"})
        self.tenant_context(owner_tenant_id)
        self.tenant_context(grantee_tenant_id)
        effective_from = self._as_utc(effective_from)
        expires_at = self._as_utc(expires_at)
        if not purposes or expires_at <= effective_from:
            raise DomainError(
                "MISSION_422",
                "请求参数不满足接口要求",
                {"field_errors": ["purpose and valid grant dates are required"]},
            )
        normalized = {
            "owner_tenant_id": owner_tenant_id,
            "grantee_tenant_id": grantee_tenant_id,
            "purpose": sorted(set(purposes)),
            "asset_types": sorted(set(asset_types)),
            "sample_ids": sorted(set(sample_ids)),
            "effective_from": effective_from.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "ACTIVE",
        }
        fingerprint = self._fingerprint({"action": "tenant_data_grant", **normalized})

        def operation() -> dict:
            grant = TenantDataGrantModel(
                id=f"grant_{uuid4().hex}",
                owner_tenant_id=owner_tenant_id,
                grantee_tenant_id=grantee_tenant_id,
                data_scope={
                    "asset_types": normalized["asset_types"],
                    "sample_ids": normalized["sample_ids"],
                },
                purpose=normalized["purpose"],
                effective_from=effective_from,
                expires_at=expires_at,
                status="ACTIVE",
            )
            self.session.add(grant)
            self.audit(
                tenant_id=grantee_tenant_id,
                actor=actor.id,
                action="tenant_data_grant_created",
                resource_type="tenant_data_grants",
                resource_id=grant.id,
                request_meta=request_meta,
            )
            return {"id": grant.id, **normalized}

        return self.run_idempotent(
            actor.home_tenant_id,
            "POST",
            "data-grant",
            idempotency_key,
            fingerprint,
            operation,
        )

    def require_data_grant(
        self,
        owner_tenant_id: str,
        grantee_tenant_id: str,
        purpose: str,
        asset_types: list[str],
        sample_ids: list[str],
        now: datetime | None = None,
    ) -> bool:
        if owner_tenant_id == grantee_tenant_id:
            return True
        current_time = self._as_utc(now or datetime.now(timezone.utc))
        requested_assets = set(asset_types)
        requested_samples = set(sample_ids)
        grants = self.session.scalars(
            select(TenantDataGrantModel).where(
                TenantDataGrantModel.owner_tenant_id == owner_tenant_id,
                TenantDataGrantModel.grantee_tenant_id == grantee_tenant_id,
                TenantDataGrantModel.status == "ACTIVE",
            )
        )
        for grant in grants:
            effective_from = self._as_utc(grant.effective_from)
            expires_at = self._as_utc(grant.expires_at)
            grant_assets = set(grant.data_scope.get("asset_types", []))
            grant_samples = set(grant.data_scope.get("sample_ids", []))
            if (
                effective_from <= current_time < expires_at
                and purpose in grant.purpose
                and requested_assets.issubset(grant_assets)
                and requested_samples.issubset(grant_samples)
            ):
                return True
        raise DomainError(
            "DATA_GRANT_412",
            "数据未获得训练、评估或跨租户统计授权",
            {
                "owner_tenant_id": owner_tenant_id,
                "grantee_tenant_id": grantee_tenant_id,
                "purpose": purpose,
                "missing_scope": {
                    "asset_types": sorted(requested_assets),
                    "sample_ids": sorted(requested_samples),
                },
            },
        )

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        encoded = dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
