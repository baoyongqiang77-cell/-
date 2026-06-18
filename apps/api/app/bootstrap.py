from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.constants import ALL_FEATURES, CUSTOMER_DEFAULT_FEATURES

from .models import (
    RoleModel,
    TenantFeatureEntitlementModel,
    TenantModel,
    UserModel,
    UserTenantRoleModel,
)


TENANTS = (
    ("t_jxjtsz_platform", "江西省交投数智科技有限公司", "PLATFORM_OPERATOR"),
    ("t_customer_001", "高速公路运营管理分中心A", "CUSTOMER_TENANT"),
    ("t_customer_002", "高速公路运营管理分中心B", "CUSTOMER_TENANT"),
)

ROLES = (
    ("PLATFORM_ADMIN", "平台管理员"),
    ("PLATFORM_OPS", "平台运维员"),
    ("ALGORITHM_ENGINEER", "算法工程师"),
    ("ANNOTATION_ADMIN", "标注管理员"),
    ("FLIGHT_ADMIN", "飞控管理员"),
    ("FLIGHT_OPERATOR", "飞控操作员"),
    ("ANALYSIS_VIEWER", "分析查看员"),
    ("AUDIT_VIEWER", "审计查看员"),
)

USERS = (
    ("u_platform_admin", "平台管理员", "t_jxjtsz_platform"),
    ("u_customer_a_operator", "分中心A飞控操作员", "t_customer_001"),
    ("u_customer_b_operator", "分中心B飞控操作员", "t_customer_002"),
)

USER_ROLES = (
    ("u_platform_admin", "t_jxjtsz_platform", "PLATFORM_ADMIN"),
    ("u_customer_a_operator", "t_customer_001", "FLIGHT_OPERATOR"),
    ("u_customer_a_operator", "t_customer_001", "ANALYSIS_VIEWER"),
    ("u_customer_b_operator", "t_customer_002", "FLIGHT_OPERATOR"),
    ("u_customer_b_operator", "t_customer_002", "ANALYSIS_VIEWER"),
)


def bootstrap_u0(session: Session) -> None:
    for tenant_id, name, tenant_type in TENANTS:
        if session.get(TenantModel, tenant_id) is None:
            session.add(
                TenantModel(
                    id=tenant_id,
                    name=name,
                    tenant_type=tenant_type,
                    status="ACTIVE",
                )
            )

    for code, name in ROLES:
        if session.get(RoleModel, code) is None:
            session.add(RoleModel(code=code, name=name))

    session.flush()

    for user_id, name, home_tenant_id in USERS:
        if session.get(UserModel, user_id) is None:
            session.add(
                UserModel(
                    id=user_id,
                    name=name,
                    home_tenant_id=home_tenant_id,
                    status="ACTIVE",
                )
            )

    session.flush()

    for user_id, tenant_id, role_code in USER_ROLES:
        existing = session.scalar(
            select(UserTenantRoleModel.id).where(
                UserTenantRoleModel.user_id == user_id,
                UserTenantRoleModel.tenant_id == tenant_id,
                UserTenantRoleModel.role_code == role_code,
            )
        )
        if existing is None:
            session.add(
                UserTenantRoleModel(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role_code=role_code,
                )
            )

    entitlement_sets = {
        "t_jxjtsz_platform": ALL_FEATURES,
        "t_customer_001": CUSTOMER_DEFAULT_FEATURES,
        "t_customer_002": CUSTOMER_DEFAULT_FEATURES,
    }
    for tenant_id, features in entitlement_sets.items():
        for feature in features:
            existing = session.scalar(
                select(TenantFeatureEntitlementModel.id).where(
                    TenantFeatureEntitlementModel.tenant_id == tenant_id,
                    TenantFeatureEntitlementModel.feature_code == feature.value,
                )
            )
            if existing is None:
                session.add(
                    TenantFeatureEntitlementModel(
                        tenant_id=tenant_id,
                        feature_code=feature.value,
                    )
                )

    session.commit()
