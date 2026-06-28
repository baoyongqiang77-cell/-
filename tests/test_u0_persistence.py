import os
import sys
import unittest
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=Warning,
    module="fastapi.testclient",
)

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy import UniqueConstraint


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.database import build_session_factory, database_url
from app.bootstrap import bootstrap_u0
from app.main import create_app
from app.models import (
    AuditLogModel,
    Base,
    IdempotencyRecordModel,
    RoleModel,
    TenantFeatureEntitlementModel,
    TenantModel,
)
from app.repositories import RequestMeta, U0Repository
from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError


EXPECTED_TABLES = {
    "tenants",
    "users",
    "roles",
    "user_tenant_roles",
    "tenant_feature_entitlements",
    "tenant_data_grants",
    "audit_logs",
    "idempotency_records",
    "devices",
    "docks",
    "road_assets",
    "bridge_assets",
    "slope_assets",
    "coordinate_transforms",
    "routes",
    "route_versions",
    "missions",
    "mission_approvals",
    "mission_dispatch_receipts",
    "flight_events",
    "flight_exception_links",
    "media_files",
    "media_chunks",
}


class DatabaseConfigurationTests(unittest.TestCase):
    def test_build_session_factory_uses_explicit_sqlite_url(self):
        factory = build_session_factory("sqlite+pysqlite:///:memory:")

        with factory() as session:
            self.assertEqual(session.bind.dialect.name, "sqlite")

    def test_database_url_defaults_to_local_sqlite_file(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                database_url(),
                "sqlite+pysqlite:///./var/u0.db",
            )


class U0ModelTests(unittest.TestCase):
    def test_metadata_contains_exact_u0_tables(self):
        self.assertEqual(set(Base.metadata.tables), EXPECTED_TABLES)

    def test_idempotency_scope_is_composite_unique(self):
        table = Base.metadata.tables["idempotency_records"]
        unique_columns = {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }

        self.assertIn(
            ("tenant_id", "http_method", "route_id", "idempotency_key"),
            unique_columns,
        )

    def test_alembic_upgrade_downgrade_upgrade_sqlite(self):
        with TemporaryDirectory() as temp_dir:
            database_path = (Path(temp_dir) / "migration.db").as_posix()
            url = f"sqlite+pysqlite:///{database_path}"
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", url)

            command.upgrade(config, "head")
            engine = create_engine(url)
            try:
                self.assertEqual(
                    set(inspect(engine).get_table_names()),
                    EXPECTED_TABLES | {"alembic_version"},
                )
            finally:
                engine.dispose()

            command.downgrade(config, "base")
            engine = create_engine(url)
            try:
                self.assertEqual(
                    inspect(engine).get_table_names(),
                    ["alembic_version"],
                )
            finally:
                engine.dispose()

            command.upgrade(config, "head")
            engine = create_engine(url)
            try:
                self.assertEqual(
                    set(inspect(engine).get_table_names()),
                    EXPECTED_TABLES | {"alembic_version"},
                )
            finally:
                engine.dispose()


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.session_factory = build_session_factory("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.session_factory.kw["bind"])
        self.session = self.session_factory()

    def tearDown(self):
        self.session.close()
        self.session_factory.kw["bind"].dispose()


class BootstrapTests(DatabaseTestCase):
    def test_bootstrap_is_repeatable_and_preserves_fixed_defaults(self):
        bootstrap_u0(self.session)
        bootstrap_u0(self.session)

        self.assertEqual(self.session.scalar(select(func.count(TenantModel.id))), 3)
        self.assertEqual(self.session.scalar(select(func.count(RoleModel.code))), 8)
        customer = U0Repository(self.session).tenant_context("t_customer_001")
        self.assertEqual(
            customer.features,
            {
                FeatureCode.FLIGHT_CONTROL,
                FeatureCode.VISION_ANALYSIS_RESULT,
                FeatureCode.DATA_ANNOTATION,
            },
        )

    def test_actor_roles_are_loaded_from_current_tenant(self):
        bootstrap_u0(self.session)

        actor = U0Repository(self.session).actor(
            "u_platform_admin", "t_jxjtsz_platform"
        )

        self.assertIn("PLATFORM_ADMIN", actor.roles)


class IdempotencyRepositoryTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        bootstrap_u0(self.session)
        self.repository = U0Repository(self.session)

    def test_same_key_can_be_reused_by_different_routes(self):
        first = self.repository.run_idempotent(
            "t_jxjtsz_platform",
            "POST",
            "feature-entitlement",
            "same-key",
            "fingerprint-1",
            lambda: {"kind": "feature"},
        )
        second = self.repository.run_idempotent(
            "t_jxjtsz_platform",
            "POST",
            "data-grant",
            "same-key",
            "fingerprint-2",
            lambda: {"kind": "grant"},
        )

        self.assertNotEqual(first, second)
        self.assertEqual(
            self.session.scalar(select(func.count(IdempotencyRecordModel.id))),
            2,
        )

    def test_conflicting_fingerprint_raises_idemp_409(self):
        self.repository.run_idempotent(
            "t_jxjtsz_platform",
            "POST",
            "feature-entitlement",
            "conflict-key",
            "fingerprint-1",
            lambda: {"ok": True},
        )

        with self.assertRaises(DomainError) as raised:
            self.repository.run_idempotent(
                "t_jxjtsz_platform",
                "POST",
                "feature-entitlement",
                "conflict-key",
                "fingerprint-2",
                lambda: {"ok": False},
            )

        self.assertEqual(raised.exception.code, "IDEMP_409")

    def test_platform_admin_enables_feature_once_with_replay(self):
        actor = self.repository.actor("u_platform_admin", "t_jxjtsz_platform")
        request_meta = RequestMeta("req_feature_001", "127.0.0.1")

        first = self.repository.enable_feature(
            actor,
            "t_customer_001",
            FeatureCode.MODEL_TRAINING,
            "feature-key",
            request_meta,
        )
        replay = self.repository.enable_feature(
            actor,
            "t_customer_001",
            FeatureCode.MODEL_TRAINING,
            "feature-key",
            request_meta,
        )

        self.assertEqual(replay, first)
        self.assertEqual(
            self.session.scalar(
                select(func.count(TenantFeatureEntitlementModel.id)).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code
                    == FeatureCode.MODEL_TRAINING.value,
                )
            ),
            1,
        )


class DataGrantRepositoryTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        bootstrap_u0(self.session)
        self.repository = U0Repository(self.session)
        self.actor = self.repository.actor(
            "u_platform_admin", "t_jxjtsz_platform"
        )
        self.now = datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc)

    def _create_grant(
        self,
        effective_from: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        self.repository.create_data_grant(
            actor=self.actor,
            owner_tenant_id="t_customer_001",
            grantee_tenant_id="t_jxjtsz_platform",
            purposes=["training"],
            asset_types=["road"],
            sample_ids=["sample_001"],
            effective_from=effective_from or self.now - timedelta(hours=1),
            expires_at=expires_at or self.now + timedelta(days=1),
            idempotency_key="grant-key",
            request_meta=RequestMeta("req_grant_001", "127.0.0.1"),
        )

    def test_active_grant_allows_matching_scope(self):
        self._create_grant()

        self.assertTrue(
            self.repository.require_data_grant(
                owner_tenant_id="t_customer_001",
                grantee_tenant_id="t_jxjtsz_platform",
                purpose="training",
                asset_types=["road"],
                sample_ids=["sample_001"],
                now=self.now,
            )
        )

    def test_not_yet_effective_grant_is_denied(self):
        self._create_grant(effective_from=self.now + timedelta(minutes=1))

        self._assert_grant_denied("training", ["road"], ["sample_001"])

    def test_expired_grant_is_denied(self):
        self._create_grant(expires_at=self.now - timedelta(minutes=1))

        self._assert_grant_denied("training", ["road"], ["sample_001"])

    def test_wrong_purpose_is_denied(self):
        self._create_grant()

        self._assert_grant_denied("evaluation", ["road"], ["sample_001"])

    def test_wrong_asset_type_is_denied(self):
        self._create_grant()

        self._assert_grant_denied("training", ["bridge"], ["sample_001"])

    def test_sample_outside_scope_is_denied(self):
        self._create_grant()

        self._assert_grant_denied("training", ["road"], ["sample_002"])

    def _assert_grant_denied(
        self,
        purpose: str,
        asset_types: list[str],
        sample_ids: list[str],
    ) -> None:
        with self.assertRaises(DomainError) as raised:
            self.repository.require_data_grant(
                owner_tenant_id="t_customer_001",
                grantee_tenant_id="t_jxjtsz_platform",
                purpose=purpose,
                asset_types=asset_types,
                sample_ids=sample_ids,
                now=self.now,
            )
        self.assertEqual(raised.exception.code, "DATA_GRANT_412")


class AuditTransactionTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        bootstrap_u0(self.session)

    def test_domain_error_preserves_request_id(self):
        error = DomainError(
            "PERM_403",
            "权限不足",
            request_id="req_review_001",
        )

        self.assertEqual(error.to_response()["request_id"], "req_review_001")

    def test_denial_audit_commits_after_business_rollback(self):
        repository = U0Repository(self.session)
        customer = repository.actor("u_customer_a_operator", "t_customer_001")
        request_meta = RequestMeta("req_denied_001", "127.0.0.1")

        with self.assertRaises(DomainError) as raised:
            repository.enable_feature(
                customer,
                "t_customer_001",
                FeatureCode.MODEL_TRAINING,
                "denied-key",
                request_meta,
            )
        self.session.rollback()
        U0Repository.commit_denial_audit(
            self.session_factory,
            tenant_id="t_customer_001",
            actor=customer.id,
            action="admin_write_denied",
            resource_type="admin_api",
            request_meta=request_meta,
            code=raised.exception.code,
        )

        with self.session_factory() as verification_session:
            audit = verification_session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_denied_001"
                )
            )
            self.assertIsNotNone(audit)
            self.assertEqual(audit.code, "PERM_403")
            self.assertEqual(audit.client_ip, "127.0.0.1")
            self.assertIsNotNone(audit.created_at)
            self.assertEqual(
                verification_session.scalar(
                    select(func.count(TenantFeatureEntitlementModel.id)).where(
                        TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                        TenantFeatureEntitlementModel.feature_code
                        == FeatureCode.MODEL_TRAINING.value,
                    )
                ),
                0,
            )


class ApiPersistenceTests(unittest.TestCase):
    def test_app_startup_rejects_unmigrated_database(self):
        with TemporaryDirectory() as temp_dir:
            database_path = (Path(temp_dir) / "unmigrated.db").as_posix()
            url = f"sqlite+pysqlite:///{database_path}"

            with self.assertRaisesRegex(RuntimeError, "database migration"):
                with TestClient(create_app(database_url_override=url)):
                    pass

    def test_feature_entitlement_and_idempotency_survive_app_restart(self):
        with TemporaryDirectory() as temp_dir:
            database_path = (Path(temp_dir) / "restart.db").as_posix()
            url = f"sqlite+pysqlite:///{database_path}"
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", url)
            command.upgrade(config, "head")
            factory = build_session_factory(url)
            try:
                with factory() as session:
                    bootstrap_u0(session)

                headers = {
                    "Authorization": "Bearer demo-platform",
                    "Idempotency-Key": "restart-feature-key",
                }
                with TestClient(create_app(database_url_override=url)) as first_client:
                    first = first_client.post(
                        "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
                        json={"feature_code": "MODEL_TRAINING"},
                        headers=headers,
                    )
                    self.assertEqual(first.status_code, 200)

                with TestClient(create_app(database_url_override=url)) as second_client:
                    replay = second_client.post(
                        "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
                        json={"feature_code": "MODEL_TRAINING"},
                        headers=headers,
                    )
                    context = second_client.get(
                        "/api/v1/tenant-context",
                        headers={"Authorization": "Bearer demo-customer-a"},
                    )

                self.assertEqual(replay.status_code, 200)
                self.assertEqual(replay.json(), first.json())
                self.assertIn("MODEL_TRAINING", context.json()["features"])
            finally:
                factory.kw["bind"].dispose()


if __name__ == "__main__":
    unittest.main()
