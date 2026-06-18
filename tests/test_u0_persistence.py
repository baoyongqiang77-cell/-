import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy import UniqueConstraint


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.database import build_session_factory, database_url
from app.bootstrap import bootstrap_u0
from app.models import Base, RoleModel, TenantModel
from app.repositories import U0Repository
from drone_inspection.constants import FeatureCode


EXPECTED_TABLES = {
    "tenants",
    "users",
    "roles",
    "user_tenant_roles",
    "tenant_feature_entitlements",
    "tenant_data_grants",
    "audit_logs",
    "idempotency_records",
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


if __name__ == "__main__":
    unittest.main()
