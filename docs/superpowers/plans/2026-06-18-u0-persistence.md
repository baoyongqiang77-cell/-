# U0 Core Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the U0 API's in-memory state with durable SQLAlchemy/Alembic persistence while preserving tenant, RBAC, entitlement, data-grant, audit, idempotency, and error contracts.

**Architecture:** Keep the existing FastAPI modular monolith and domain constants. Add a request-scoped SQLAlchemy session, focused ORM models, a U0 repository, and idempotent bootstrap data. SQLite file databases drive fast automated tests; a dedicated PostgreSQL Compose service verifies Alembic upgrade/downgrade compatibility without claiming production acceptance.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, Psycopg 3, PostgreSQL 16, SQLite, `unittest`, Docker Compose.

---

## File Map

- Create `apps/api/app/database.py`: database URL settings, engine/session construction, request session dependency.
- Create `apps/api/app/models.py`: the eight U0 ORM tables and database constraints.
- Create `apps/api/app/repositories.py`: tenant-scoped reads, RBAC, grants, audits, and idempotent writes.
- Create `apps/api/app/bootstrap.py`: repeatable platform/customer/demo identity initialization.
- Create `scripts/bootstrap_u0.py`: explicit bootstrap command; application startup never silently seeds production data.
- Modify `apps/api/app/dependencies.py`: resolve demo tokens to persisted users and roles.
- Modify `apps/api/app/main.py`: app factory database injection, request IDs, repository-backed routes and transactions.
- Modify `apps/api/requirements.txt`: SQLAlchemy, Alembic, Psycopg dependencies.
- Create `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`: migration runner.
- Create `alembic/versions/20260618_0001_u0_core_tables.py`: reversible initial schema.
- Create `tests/test_u0_persistence.py`: model, bootstrap, repository, persistence, and transaction tests.
- Modify `tests/test_api_u0_app.py`: persistent API and RBAC regression tests.
- Create `infra/compose/docker-compose.persistence-test.yml`: isolated PostgreSQL migration test service.
- Create `scripts/test_postgres_migrations.ps1`: repeatable upgrade/downgrade/upgrade smoke test.
- Modify `README.md`: `.venv`, migration, and test commands.
- Modify `docs/60-test-reports/U0-foundation-test-report.md`: persistence evidence and remaining boundaries.

## Task 1: Reproducible Python Environment and Database Session

**Files:**
- Modify: `apps/api/requirements.txt`
- Create: `apps/api/app/database.py`
- Create: `tests/test_u0_persistence.py`

- [ ] **Step 1: Add a failing database configuration test**

```python
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
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u0_persistence.DatabaseConfigurationTests -v
```

Expected: import failure for `app.database` because the module does not exist.

- [ ] **Step 3: Pin compatible dependency ranges and create the local environment**

Set `apps/api/requirements.txt` to:

```text
fastapi==0.137.1
httpx==0.28.1
SQLAlchemy>=2.0,<3.0
alembic>=1.13,<2.0
psycopg[binary]>=3.1,<4.0
```

Run:

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r apps\api\requirements.txt
```

Expected: installation exits with code 0; `.venv` remains ignored by Git.

- [ ] **Step 4: Implement the minimal database module**

```python
from collections.abc import Generator
import os

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./var/u0.db"


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def build_session_factory(url: str):
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if parsed.get_backend_name() == "sqlite" else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def session_dependency(request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 5: Run the focused test and confirm GREEN**

Run the command from Step 2. Expected: 2 tests pass.

- [ ] **Step 6: Commit the environment and session foundation**

```powershell
git add apps/api/requirements.txt apps/api/app/database.py tests/test_u0_persistence.py
git commit -m "build: add U0 database session foundation"
```

## Task 2: Eight U0 ORM Tables and Reversible Alembic Migration

**Files:**
- Create: `apps/api/app/models.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/20260618_0001_u0_core_tables.py`
- Modify: `tests/test_u0_persistence.py`

- [ ] **Step 1: Add failing metadata and constraint tests**

```python
EXPECTED_TABLES = {
    "tenants", "users", "roles", "user_tenant_roles",
    "tenant_feature_entitlements", "tenant_data_grants",
    "audit_logs", "idempotency_records",
}


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
```

- [ ] **Step 2: Run the model tests and confirm RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u0_persistence.U0ModelTests -v
```

Expected: import failure for `app.models`.

- [ ] **Step 3: Implement typed ORM models**

Create `Base(DeclarativeBase)` and these exact table fields:

```text
tenants: id PK, name, tenant_type, status, created_at, updated_at
users: id PK, name, home_tenant_id FK, status, created_at, updated_at
roles: code PK, name
user_tenant_roles: id PK, user_id FK, tenant_id FK, role_code FK, created_at,
  UNIQUE(user_id, tenant_id, role_code)
tenant_feature_entitlements: id PK, tenant_id FK, feature_code, created_at,
  UNIQUE(tenant_id, feature_code)
tenant_data_grants: id PK, owner_tenant_id FK, grantee_tenant_id FK,
  data_scope JSON, purpose JSON, effective_from, expires_at, status, created_at
audit_logs: id PK, tenant_id FK, actor, action, resource_type, resource_id,
  client_ip, request_id INDEX, code, before_status, after_status, created_at INDEX
idempotency_records: id PK, tenant_id FK, http_method, route_id,
  idempotency_key, request_fingerprint, response JSON, created_at,
  UNIQUE(tenant_id, http_method, route_id, idempotency_key)
```

Use UTC-aware `DateTime(timezone=True)`, JSON values with plain lists/dicts, foreign keys with no cascading tenant deletion, and check constraints limiting `tenant_type` to the two fixed values.

- [ ] **Step 4: Create Alembic configuration and the explicit migration**

Configure `alembic/env.py` to read `DATABASE_URL`, import `Base.metadata`, and enable `render_as_batch=True` only for SQLite. The migration `upgrade()` creates the eight tables in dependency order; `downgrade()` drops them in reverse dependency order. Do not use database-specific enum types for fixed strings because SQLite and PostgreSQL must share the migration.

- [ ] **Step 5: Run model and SQLite migration tests**

Add and run:

```python
def test_alembic_upgrade_and_downgrade_sqlite(self):
    with TemporaryDirectory() as temp_dir:
        url = f"sqlite+pysqlite:///{Path(temp_dir) / 'migration.db'}"
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
        self.assertEqual(set(inspect(create_engine(url)).get_table_names()), EXPECTED_TABLES)
        command.downgrade(config, "base")
        self.assertEqual(inspect(create_engine(url)).get_table_names(), [])
        command.upgrade(config, "head")
        self.assertEqual(set(inspect(create_engine(url)).get_table_names()), EXPECTED_TABLES)
```

Expected: model and migration tests pass.

- [ ] **Step 6: Commit schema and migration**

```powershell
git add apps/api/app/models.py alembic.ini alembic tests/test_u0_persistence.py
git commit -m "feat: add U0 core database schema"
```

## Task 3: Idempotent Bootstrap and Persisted RBAC

**Files:**
- Create: `apps/api/app/bootstrap.py`
- Create: `apps/api/app/repositories.py`
- Create: `scripts/bootstrap_u0.py`
- Modify: `apps/api/app/dependencies.py`
- Modify: `tests/test_u0_persistence.py`

- [ ] **Step 1: Add failing bootstrap and actor tests**

```python
class BootstrapTests(DatabaseTestCase):
    def test_bootstrap_is_repeatable_and_preserves_fixed_defaults(self):
        bootstrap_u0(self.session)
        bootstrap_u0(self.session)
        self.assertEqual(self.session.scalar(select(func.count(Tenant.id))), 3)
        self.assertEqual(self.session.scalar(select(func.count(Role.code))), 8)
        customer = U0Repository(self.session).tenant_context("t_customer_001")
        self.assertEqual(
            customer.features,
            {FeatureCode.FLIGHT_CONTROL, FeatureCode.VISION_ANALYSIS_RESULT, FeatureCode.DATA_ANNOTATION},
        )

    def test_actor_roles_are_loaded_from_current_tenant(self):
        actor = U0Repository(self.session).actor("u_platform_admin", "t_jxjtsz_platform")
        self.assertIn("PLATFORM_ADMIN", actor.roles)
```

- [ ] **Step 2: Run and confirm RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u0_persistence.BootstrapTests -v
```

Expected: import failure for `bootstrap_u0` or `U0Repository`.

- [ ] **Step 3: Implement fixed bootstrap rows**

Implement `bootstrap_u0(session: Session) -> None` using select-before-insert behavior inside one transaction. Seed exactly three tenants, three demo users, eight role definitions, demo user role links, all eight platform feature entitlements, and the three fixed customer defaults. Never delete or overwrite existing non-bootstrap data.

Create `scripts/bootstrap_u0.py` as the explicit command that opens `database_url()`, calls `bootstrap_u0`, reports inserted/existing counts, and exits nonzero on failure. API startup must not silently create demo users or tenants; tests and development setup invoke this command deliberately.

- [ ] **Step 4: Implement repository read contracts**

```python
@dataclass(frozen=True)
class PersistedActor:
    id: str
    name: str
    home_tenant_id: str
    roles: tuple[str, ...]


class U0Repository:
    def __init__(self, session: Session): ...
    def actor(self, user_id: str, tenant_id: str) -> PersistedActor: ...
    def tenant_context(self, tenant_id: str) -> TenantContext: ...
    def switchable_tenant_ids(self, actor: PersistedActor) -> list[str]: ...
    def require_role(self, actor: PersistedActor, allowed: set[str]) -> None: ...
```

`switchable_tenant_ids` returns all tenants only when the home tenant is `PLATFORM_OPERATOR` and the actor has `PLATFORM_ADMIN` or `PLATFORM_OPS`; otherwise it returns only the home tenant. Missing users return `AUTH_401`; missing or inaccessible tenants use the existing tenant errors.

- [ ] **Step 5: Replace token payloads with persisted identity IDs**

Keep demo token strings, but map each token only to a user ID. `actor_from_authorization` receives a request session and calls `repository.actor`; role names are no longer trusted from in-memory token constants.

- [ ] **Step 6: Run focused tests and the existing API suite**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u0_persistence.BootstrapTests tests.test_api_u0_app -v
```

Expected: all focused and existing API tests pass.

- [ ] **Step 7: Commit bootstrap and RBAC reads**

```powershell
git add apps/api/app/bootstrap.py apps/api/app/repositories.py apps/api/app/dependencies.py scripts/bootstrap_u0.py tests
git commit -m "feat: persist U0 bootstrap identities and RBAC"
```

## Task 4: Scoped Idempotency and Atomic Admin Writes

**Files:**
- Modify: `apps/api/app/repositories.py`
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_u0_persistence.py`
- Modify: `tests/test_api_u0_app.py`

- [ ] **Step 1: Add failing scoped idempotency tests**

```python
def test_same_key_can_be_reused_by_different_routes(self):
    first = repository.run_idempotent("t_jxjtsz_platform", "POST", "feature-entitlement", "same", "fp1", lambda: {"kind": "feature"})
    second = repository.run_idempotent("t_jxjtsz_platform", "POST", "data-grant", "same", "fp2", lambda: {"kind": "grant"})
    self.assertNotEqual(first, second)

def test_conflicting_fingerprint_raises_idemp_409(self):
    repository.run_idempotent("t_jxjtsz_platform", "POST", "feature-entitlement", "key", "fp1", lambda: {"ok": True})
    with self.assertRaisesRegex(DomainError, "幂等键冲突"):
        repository.run_idempotent("t_jxjtsz_platform", "POST", "feature-entitlement", "key", "fp2", lambda: {"ok": False})
```

- [ ] **Step 2: Run and confirm RED**

Expected: `run_idempotent` is missing.

- [ ] **Step 3: Implement transaction-scoped idempotency**

Implement `run_idempotent(tenant_id, http_method, route_id, key, fingerprint, operation)` so it validates the key, reads any existing scoped record, rejects fingerprint conflicts with `IDEMP_409`, executes the operation once, stores the JSON result, and commits business mutation plus success audit plus idempotency record atomically. Catch `IntegrityError`, roll back, reload the winning row, then replay or reject by fingerprint.

- [ ] **Step 4: Move feature entitlement writes into the repository**

Implement:

```python
def enable_feature(self, actor, tenant_id, feature_code, request_meta) -> dict
```

Require `PLATFORM_ADMIN`, validate the target tenant before creating the idempotency record, insert entitlement only if absent, write `feature_entitlement_enabled` audit, and return the existing API response fields.

- [ ] **Step 5: Run focused and API idempotency tests**

Expected: replay, conflict, route reuse, invalid tenant, and missing-key tests pass with no duplicate rows.

- [ ] **Step 6: Commit atomic feature writes**

```powershell
git add apps/api/app/repositories.py apps/api/app/main.py tests
git commit -m "feat: persist scoped idempotent U0 writes"
```

## Task 5: Time-Bounded Data Grants

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/repositories.py`
- Modify: `tests/test_u0_persistence.py`
- Modify: `tests/test_api_u0_app.py`

- [ ] **Step 1: Add failing grant validation tests**

Add API fields and repository tests for `asset_types`, `effective_from`, and `expires_at`. Cover not-yet-effective, expired, wrong purpose, wrong asset type, and sample IDs outside scope; each denial must return `DATA_GRANT_412`.

```python
grant = repository.create_data_grant(
    actor=platform_admin,
    owner_tenant_id="t_customer_001",
    grantee_tenant_id="t_jxjtsz_platform",
    purposes=["training"],
    asset_types=["road"],
    sample_ids=["sample_001"],
    effective_from=now - timedelta(hours=1),
    expires_at=now + timedelta(days=1),
    request_meta=request_meta,
)
self.assertTrue(repository.require_data_grant(..., now=now))
```

- [ ] **Step 2: Run and confirm RED**

Expected: request schema rejects the new fields or repository methods are missing.

- [ ] **Step 3: Extend Pydantic request schemas**

`DataScopeRequest` contains `asset_types: list[str]` and `sample_ids: list[str]`. `TenantDataGrantRequest` contains timezone-aware `effective_from` and `expires_at`, and validates `expires_at > effective_from`. Invalid time ranges use the existing `MISSION_422` validation envelope.

- [ ] **Step 4: Implement grant persistence and authorization checks**

`create_data_grant` requires `PLATFORM_ADMIN`, both tenants, non-empty purpose, and valid dates. `require_data_grant` accepts owner, grantee, purpose, asset types, sample IDs, and injected `now`; it grants only when every dimension is contained and status equals existing `ACTIVE`.

- [ ] **Step 5: Run grant tests and API regression**

Expected: all grant boundaries pass and existing API responses retain prior fields plus `asset_types`, `effective_from`, and `expires_at`.

- [ ] **Step 6: Commit bounded grants**

```powershell
git add apps/api/app/main.py apps/api/app/repositories.py tests
git commit -m "feat: persist time-bounded tenant data grants"
```

## Task 6: Request-Linked Audits and Rejected-Request Transactions

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/dependencies.py`
- Modify: `apps/api/app/repositories.py`
- Modify: `tests/test_u0_persistence.py`
- Modify: `tests/test_api_u0_app.py`

- [ ] **Step 1: Add failing request-ID and denial audit tests**

```python
def test_denial_rolls_back_business_write_but_commits_audit(self):
    response = client.post(..., headers={"X-Request-Id": "req_review_001", "Authorization": "Bearer demo-customer-a", ...})
    self.assertEqual(response.status_code, 403)
    self.assertEqual(response.json()["request_id"], "req_review_001")
    audit = persisted_audit("req_review_001")
    self.assertEqual(audit.code, "PERM_403")
    self.assertEqual(audit.client_ip, "testclient")
    self.assertIsNotNone(audit.created_at)
    self.assertEqual(entitlement_count(...), 0)
```

- [ ] **Step 2: Run and confirm RED**

Expected: response generates a different request ID and audit fields are absent.

- [ ] **Step 3: Add request metadata middleware**

At request start, validate optional `X-Request-Id` against `^[A-Za-z0-9_.:-]{1,128}$`; otherwise generate `req_<hex>`. Store it on `request.state.request_id` and expose a `RequestMeta(request_id, client_ip)` dependency. Modify `DomainError` to accept an optional request ID so handlers preserve the request-scoped value.

- [ ] **Step 4: Implement independent denial audit transaction**

On role, tenant-switch, feature, or data-grant denial: roll back the request session; open a fresh session from `app.state.session_factory`; insert the denial audit with request ID and client IP; commit it; return the original fixed domain error. If audit commit fails, log only safe structured fields and never allow the denied operation.

- [ ] **Step 5: Enforce audit query RBAC and tenant filtering**

Allow platform `PLATFORM_ADMIN` and `AUDIT_VIEWER` to use the existing admin audit query. Keep customer access denied in this increment. Return the new audit fields without exposing database internals.

- [ ] **Step 6: Run audit, RBAC, and API tests**

Expected: successful and denied operations have persisted request-linked audits; denial business changes remain absent.

- [ ] **Step 7: Commit audit transaction handling**

```powershell
git add src/drone_inspection/errors.py apps/api/app tests
git commit -m "feat: persist request-linked U0 audits"
```

## Task 7: App Restart Persistence and PostgreSQL Migration Smoke Test

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_api_u0_app.py`
- Create: `infra/compose/docker-compose.persistence-test.yml`
- Create: `scripts/test_postgres_migrations.ps1`

- [ ] **Step 1: Add a failing restart persistence API test**

Migrate and bootstrap an explicit SQLite file URL, create an app against it, enable a feature and add a grant, close its client, create a second app using the same URL, then assert the feature, grant, audit, and idempotent replay still exist.

- [ ] **Step 2: Run and confirm RED**

Expected: `create_app(database_url=...)` is unsupported or state disappears after restart.

- [ ] **Step 3: Make the app factory database-injectable**

Use:

```python
def create_app(database_url_override: str | None = None) -> FastAPI:
    url = database_url_override or database_url()
    app.state.session_factory = build_session_factory(url)
```

Migrations and bootstrap remain explicit deployment commands and never run at module import or silently during application startup. Application lifespan verifies connectivity and the current Alembic revision; startup fails when the database is unavailable or behind the expected revision. Do not invent a runtime 5xx error code; record that unresolved baseline item in the test report.

- [ ] **Step 4: Add isolated PostgreSQL Compose service**

Define `postgres:16` with database `drone_u0_test`, test-only credentials, healthcheck, no external network dependency at runtime, and host port controlled by `U0_POSTGRES_TEST_PORT` defaulting to `55432`.

- [ ] **Step 5: Add the migration smoke script**

The PowerShell script must:

1. Start only the persistence test service.
2. Wait for `pg_isready` health.
3. Set `DATABASE_URL=postgresql+psycopg://u0_test:u0_test@127.0.0.1:<port>/drone_u0_test`.
4. Run `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head`.
5. Run a Python inspection command asserting all eight tables.
6. Stop and remove the test container in `finally` without deleting unrelated containers or volumes.

- [ ] **Step 6: Run SQLite restart and PostgreSQL smoke tests**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_api_u0_app -v
& '.\scripts\test_postgres_migrations.ps1'
```

Expected: restart test passes; migration script exits 0 after all three migration operations.

- [ ] **Step 7: Commit restart and migration verification**

```powershell
git add apps/api/app/main.py tests/test_api_u0_app.py infra/compose scripts/test_postgres_migrations.ps1
git commit -m "test: verify U0 persistence across restart and PostgreSQL"
```

## Task 8: Documentation, Full Regression, and Remote Sync

**Files:**
- Modify: `README.md`
- Modify: `docs/60-test-reports/U0-foundation-test-report.md`

- [ ] **Step 1: Document reproducible commands**

Add `.venv` creation, dependency installation, Alembic migration, SQLite/full tests, PostgreSQL smoke test, and API startup commands. Mark demo tokens, SQLite, and the PostgreSQL smoke container as non-production facilities.

- [ ] **Step 2: Update U0 acceptance evidence**

Record the final test counts and evidence for eight tables, RBAC, persistence, data-grant dates, request-linked audits, scoped idempotency, restart behavior, and PostgreSQL migration compatibility. Keep these explicit remaining boundaries:

```text
- Production unified identity protocol remains unconfirmed.
- The generic database 5xx error code requires a signed baseline change.
- PostgreSQL smoke success is not government-cloud production database acceptance.
- Customer self-service audit query remains a later U0 increment.
```

- [ ] **Step 3: Run the complete verification suite**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\scripts\test_postgres_migrations.ps1'
git diff --check
git status --short --branch
```

Expected: all Python tests pass, PostgreSQL migration smoke passes, `git diff --check` has no output, and only intended documentation changes remain.

- [ ] **Step 4: Commit documentation**

```powershell
git add README.md docs/60-test-reports/U0-foundation-test-report.md
git commit -m "docs: record U0 persistence verification"
```

- [ ] **Step 5: Push the feature branch**

```powershell
git push origin codex/u0-api-foundation
```

Expected: local and remote `codex/u0-api-foundation` report `0 0` from `git rev-list --left-right --count origin/codex/u0-api-foundation...HEAD`.
