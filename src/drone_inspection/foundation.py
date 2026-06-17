from __future__ import annotations

from dataclasses import dataclass, field

from .constants import ALL_FEATURES, CUSTOMER_DEFAULT_FEATURES, FeatureCode
from .errors import DomainError


@dataclass
class Tenant:
    id: str
    name: str
    tenant_type: str
    status: str = "ACTIVE"


@dataclass
class TenantContext:
    tenant: Tenant
    features: set[FeatureCode]

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    @property
    def tenant_type(self) -> str:
        return self.tenant.tenant_type

    def has_feature(self, feature: FeatureCode | str) -> bool:
        return FeatureCode(feature) in self.features


@dataclass
class AuditLog:
    tenant_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str | None = None
    code: str | None = None
    before_status: str | None = None
    after_status: str | None = None


@dataclass
class DataGrant:
    owner_tenant_id: str
    grantee_tenant_id: str
    purposes: set[str]
    sample_ids: set[str]
    status: str = "ACTIVE"


class IdempotencyStore:
    def __init__(self):
        self._records: dict[str, tuple[str, object]] = {}

    def record(self, key: str, request_fingerprint: str, response):
        if key in self._records:
            previous_fingerprint, previous_response = self._records[key]
            if previous_fingerprint != request_fingerprint:
                raise DomainError(
                    "IDEMP_409",
                    "幂等键冲突",
                    {"idempotency_key": key},
                )
            return previous_response
        self._records[key] = (request_fingerprint, response)
        return response


@dataclass
class PlatformState:
    tenants: dict[str, Tenant] = field(default_factory=dict)
    entitlements: dict[str, set[FeatureCode]] = field(default_factory=dict)
    data_grants: list[DataGrant] = field(default_factory=list)
    audit_logs: list[AuditLog] = field(default_factory=list)
    idempotency: IdempotencyStore = field(default_factory=IdempotencyStore)

    @classmethod
    def bootstrap(cls) -> "PlatformState":
        state = cls()
        state.tenants["t_jxjtsz_platform"] = Tenant(
            id="t_jxjtsz_platform",
            name="江西省交投数智科技有限公司",
            tenant_type="PLATFORM_OPERATOR",
        )
        state.tenants["t_customer_001"] = Tenant(
            id="t_customer_001",
            name="高速公路运营管理分中心A",
            tenant_type="CUSTOMER_TENANT",
        )
        state.tenants["t_customer_002"] = Tenant(
            id="t_customer_002",
            name="高速公路运营管理分中心B",
            tenant_type="CUSTOMER_TENANT",
        )
        state.entitlements["t_jxjtsz_platform"] = set(ALL_FEATURES)
        state.entitlements["t_customer_001"] = set(CUSTOMER_DEFAULT_FEATURES)
        state.entitlements["t_customer_002"] = set(CUSTOMER_DEFAULT_FEATURES)
        return state

    def tenant_context(self, tenant_id: str) -> TenantContext:
        if tenant_id not in self.tenants:
            raise DomainError("TENANT_404", "租户不存在", {"tenant_id": tenant_id})
        return TenantContext(
            tenant=self.tenants[tenant_id],
            features=set(self.entitlements.get(tenant_id, set())),
        )

    def enable_feature(self, tenant_id: str, feature: FeatureCode | str) -> None:
        self.entitlements.setdefault(tenant_id, set()).add(FeatureCode(feature))

    def require_feature(self, tenant_id: str, feature: FeatureCode | str, actor: str) -> bool:
        feature = FeatureCode(feature)
        context = self.tenant_context(tenant_id)
        if context.has_feature(feature):
            return True
        self.audit(
            tenant_id=tenant_id,
            actor=actor,
            action="feature_denied",
            resource_type="feature",
            resource_id=feature.value,
            code="FEATURE_403",
        )
        raise DomainError(
            "FEATURE_403",
            "当前租户未开通目标功能",
            {"feature_code": feature.value},
        )

    def add_data_grant(
        self,
        owner_tenant_id: str,
        grantee_tenant_id: str,
        purposes: list[str],
        sample_ids: list[str],
    ) -> DataGrant:
        grant = DataGrant(
            owner_tenant_id=owner_tenant_id,
            grantee_tenant_id=grantee_tenant_id,
            purposes=set(purposes),
            sample_ids=set(sample_ids),
        )
        self.data_grants.append(grant)
        return grant

    def require_data_grant(
        self,
        owner_tenant_id: str,
        grantee_tenant_id: str,
        purpose: str,
        sample_ids: list[str],
    ) -> bool:
        if owner_tenant_id == grantee_tenant_id:
            return True
        requested = set(sample_ids)
        for grant in self.data_grants:
            if (
                grant.status == "ACTIVE"
                and grant.owner_tenant_id == owner_tenant_id
                and grant.grantee_tenant_id == grantee_tenant_id
                and purpose in grant.purposes
                and requested.issubset(grant.sample_ids)
            ):
                return True
        self.audit(
            tenant_id=grantee_tenant_id,
            actor=grantee_tenant_id,
            action="data_grant_denied",
            resource_type="tenant_data_grants",
            resource_id=owner_tenant_id,
            code="DATA_GRANT_412",
        )
        raise DomainError(
            "DATA_GRANT_412",
            "数据未获得训练、评估或跨租户统计授权",
            {
                "owner_tenant_id": owner_tenant_id,
                "grantee_tenant_id": grantee_tenant_id,
                "purpose": purpose,
            },
        )

    def object_path(
        self,
        tenant_id: str,
        project_id: str,
        mission_id: str,
        filename: str,
    ) -> str:
        return f"{tenant_id}/{project_id}/{mission_id}/{filename}"

    def audit(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        code: str | None = None,
        before_status: str | None = None,
        after_status: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            code=code,
            before_status=before_status,
            after_status=after_status,
        )
        self.audit_logs.append(log)
        return log

    def audit_contains(self, tenant_id: str, action: str, code: str | None) -> bool:
        return any(
            log.tenant_id == tenant_id and log.action == action and log.code == code
            for log in self.audit_logs
        )

