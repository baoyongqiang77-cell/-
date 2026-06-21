# U1-F02 Device and Dock Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a persistent, tenant-isolated device and dock registry with platform-only management APIs, idempotent audited writes, and normalized DJI status synchronization.

**Architecture:** Extend the existing FastAPI modular monolith with two SQLAlchemy models and a reversible Alembic migration. Keep tenant-filtered persistence and business validation in a focused `device_registry.py` module, while `main.py` only owns HTTP schemas, access checks, and eight routes. Reuse U0 authentication, controlled tenant switching, idempotency records, unified errors, and denial-audit transactions.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, SQLite, PostgreSQL 16, `unittest`, existing U1 `FlightEvent`/DJI simulator contracts.

---

## Scope and File Map

- Create `alembic/versions/20260621_0002_u1_device_registry.py`: reversible `devices` and `docks` schema.
- Modify `apps/api/app/database.py`: enable SQLite foreign-key enforcement for test fidelity.
- Modify `apps/api/app/models.py`: add device and dock ORM models with database-level tenant constraints.
- Create `apps/api/app/device_registry.py`: tenant-filtered repository, registry service, status service, and response serializers.
- Modify `apps/api/app/main.py`: advance expected migration revision, define request schemas, add access helpers and eight U1-F02 routes.
- Modify `tests/test_u0_persistence.py`: update the complete metadata table set after the additive migration.
- Create `tests/test_u1_device_registry_persistence.py`: model, migration, constraint, repository, service, idempotency, and status-event tests.
- Create `tests/test_api_u1_device_registry.py`: API, tenant, feature, role, audit, validation, and OpenAPI tests.
- Create `scripts/test_postgres_migrations.sh`: Linux/Docker equivalent of the existing isolated PowerShell migration smoke script.
- Modify `docs/60-test-reports/U1-flight-test-report.md`: add U1-F02 evidence and retained production boundaries.

Do not add a real DJI client, public internet call, delete endpoint, lifecycle state machine, GIS object, mission object, WebSocket endpoint, or customer write permission.

## Task 1: ORM Models, Foreign-Key Enforcement, and Alembic Migration

**Files:**
- Modify: `apps/api/app/database.py`
- Modify: `apps/api/app/models.py`
- Create: `alembic/versions/20260621_0002_u1_device_registry.py`
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_u0_persistence.py`
- Create: `tests/test_u1_device_registry_persistence.py`

- [ ] **Step 1: Write failing metadata and constraint tests**

Create `tests/test_u1_device_registry_persistence.py` with path setup matching `tests/test_u0_persistence.py`, then add:

```python
class DeviceRegistryModelTests(unittest.TestCase):
    def test_metadata_contains_device_registry_tables(self):
        self.assertIn("devices", Base.metadata.tables)
        self.assertIn("docks", Base.metadata.tables)

    def test_devices_register_only_documented_types_and_statuses(self):
        table = Base.metadata.tables["devices"]
        checks = {str(item.sqltext) for item in table.constraints if isinstance(item, CheckConstraint)}
        self.assertTrue(any("DOCK" in value and "EDGE_NODE" in value for value in checks))
        self.assertTrue(any("ONLINE" in value and "OFFLINE" in value for value in checks))

    def test_docks_use_composite_tenant_foreign_keys(self):
        table = Base.metadata.tables["docks"]
        references = {
            tuple(element.target_fullname for element in constraint.elements)
            for constraint in table.foreign_key_constraints
        }
        self.assertIn(("devices.tenant_id", "devices.id"), references)
```

Update `EXPECTED_TABLES` in `tests/test_u0_persistence.py` by adding `"devices"` and `"docks"`.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_device_registry_persistence.DeviceRegistryModelTests tests.test_u0_persistence.U0ModelTests -v
```

Expected: FAIL because `devices` and `docks` do not exist in `Base.metadata`.

- [ ] **Step 3: Enable SQLite foreign keys and add ORM models**

In `apps/api/app/database.py`, import `event` from SQLAlchemy. After creating the engine in `build_session_factory`, register this SQLite-only connection listener:

```python
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
```

In `apps/api/app/models.py`, explicitly import `ForeignKeyConstraint` and `text`. Add these models:

```python
class DeviceModel(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "device_type IN ('DOCK', 'DRONE', 'PAYLOAD', 'EDGE_NODE')",
            name="ck_devices_device_type",
        ),
        CheckConstraint(
            "status IS NULL OR status IN ('ONLINE', 'OFFLINE')",
            name="ck_devices_status",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_devices_tenant_id_id"),
        UniqueConstraint("serial_number", name="uq_devices_serial_number"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(16))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class DockModel(Base):
    __tablename__ = "docks"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_docks_device_id"),
        ForeignKeyConstraint(
            ["tenant_id", "device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_device",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bound_drone_device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_drone",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "edge_node_device_id"],
            ["devices.tenant_id", "devices.id"],
            name="fk_docks_tenant_edge_node",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_drone_device_id: Mapped[str | None] = mapped_column(String(64))
    edge_node_device_id: Mapped[str | None] = mapped_column(String(64))
    environment_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
```

- [ ] **Step 4: Add the reversible migration and expected revision**

Create migration revision `20260621_0002`, down revision `20260618_0001`. Its `upgrade()` must create `devices` first and `docks` second with the same columns, checks, unique constraints, composite foreign keys, and tenant indexes as the ORM. Set `docks.environment_json` to `sa.JSON(), nullable=False, server_default=sa.text("'{}'")`. Its `downgrade()` must drop `docks`, then the `devices.tenant_id` index, then `devices`.

Set in `apps/api/app/main.py`:

```python
EXPECTED_DATABASE_REVISION = "20260621_0002"
```

Do not modify the original U0 migration.

- [ ] **Step 5: Add migration round-trip and cross-tenant database tests**

Add `test_alembic_device_registry_round_trip_sqlite` that executes the following sequence and assertions:

```python
command.upgrade(config, "head")
self.assertIn("devices", inspect(engine).get_table_names())
self.assertIn("docks", inspect(engine).get_table_names())
command.downgrade(config, "20260618_0001")
self.assertNotIn("devices", inspect(engine).get_table_names())
self.assertNotIn("docks", inspect(engine).get_table_names())
command.upgrade(config, "head")
self.assertIn("devices", inspect(engine).get_table_names())
self.assertIn("docks", inspect(engine).get_table_names())
```

Add `test_database_rejects_cross_tenant_dock_relationship` using `build_session_factory`: insert a customer-A dock device and a customer-B drone, attempt a customer-A `DockModel` referencing the customer-B drone, and assert `sqlalchemy.exc.IntegrityError` on `session.flush()`.

- [ ] **Step 6: Run focused and full persistence tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_device_registry_persistence tests.test_u0_persistence -v
```

Expected: PASS with no errors; SQLite cross-tenant insertion is rejected.

- [ ] **Step 7: Commit the schema increment**

```powershell
git add apps/api/app/database.py apps/api/app/models.py apps/api/app/main.py alembic/versions/20260621_0002_u1_device_registry.py tests/test_u0_persistence.py tests/test_u1_device_registry_persistence.py
git commit -m "feat: add U1 device registry schema"
```

## Task 2: Tenant-Filtered Device Registry Repository

**Files:**
- Create: `apps/api/app/device_registry.py`
- Modify: `tests/test_u1_device_registry_persistence.py`

- [ ] **Step 1: Write failing repository isolation tests**

Add a `DeviceRegistryRepositoryTests` fixture that bootstraps U0 and inserts one device per customer tenant. Add tests asserting:

```python
def test_list_devices_is_always_tenant_filtered(self):
    items = self.repository.list_devices("t_customer_001")
    self.assertEqual([item.id for item in items], ["dev_customer_a"])

def test_cross_tenant_device_detail_returns_tenant_404(self):
    with self.assertRaises(DomainError) as raised:
        self.repository.device("t_customer_001", "dev_customer_b")
    self.assertEqual(raised.exception.code, "TENANT_404")

def test_serial_lookup_is_reserved_for_internal_status_sync(self):
    item = self.repository.device_by_serial("DOCK-A-001")
    self.assertEqual(item.tenant_id, "t_customer_001")
```

- [ ] **Step 2: Run repository tests and verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_device_registry_persistence.DeviceRegistryRepositoryTests -v
```

Expected: ERROR because `app.device_registry` and `DeviceRegistryRepository` do not exist.

- [ ] **Step 3: Implement the focused repository**

Create `apps/api/app/device_registry.py` with `DeviceRegistryRepository`. Implement these exact public methods:

```python
class DeviceRegistryRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_devices(self, tenant_id: str) -> list[DeviceModel]:
        statement = (
            select(DeviceModel)
            .where(DeviceModel.tenant_id == tenant_id)
            .order_by(DeviceModel.id)
        )
        return list(self.session.scalars(statement))

    def device(self, tenant_id: str, device_id: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(
                DeviceModel.tenant_id == tenant_id,
                DeviceModel.id == device_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "设备不存在或不可访问")
        return item

    def device_by_serial(self, serial_number: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(DeviceModel.serial_number == serial_number)
        )
        if item is None:
            raise DomainError("TENANT_404", "设备不存在或不可访问")
        return item

    def list_docks(self, tenant_id: str) -> list[DockModel]:
        statement = (
            select(DockModel)
            .where(DockModel.tenant_id == tenant_id)
            .order_by(DockModel.id)
        )
        return list(self.session.scalars(statement))

    def dock(self, tenant_id: str, dock_id: str) -> DockModel:
        item = self.session.scalar(
            select(DockModel).where(
                DockModel.tenant_id == tenant_id,
                DockModel.id == dock_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "机巢不存在或不可访问")
        return item
```

Keep `device_by_serial` out of public HTTP routes; global lookup is only for trusted status-event processing.

- [ ] **Step 4: Run repository tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Commit the repository**

```powershell
git add apps/api/app/device_registry.py tests/test_u1_device_registry_persistence.py
git commit -m "feat: add tenant-scoped device registry repository"
```

## Task 3: Registry Service, Validation, Idempotency, and Success Audits

**Files:**
- Modify: `apps/api/app/device_registry.py`
- Modify: `tests/test_u1_device_registry_persistence.py`

- [ ] **Step 1: Write failing service tests**

Add tests for these behaviors:

```python
def test_platform_service_creates_device_once_with_idempotent_replay(self):
    first = self.service.create_device(
        actor_id="u_platform_admin",
        tenant_id="t_customer_001",
        values={
            "device_type": "DOCK",
            "name": "机场一号",
            "manufacturer": "DJI",
            "model": "DJI Dock 3",
            "serial_number": "DOCK-A-001",
            "firmware_version": "1.0.0",
        },
        idempotency_key="device-create-001",
        request_meta=RequestMeta("req_device_001", "127.0.0.1"),
    )
    replay = self.service.create_device(
        actor_id="u_platform_admin",
        tenant_id="t_customer_001",
        values={
            "device_type": "DOCK",
            "name": "机场一号",
            "manufacturer": "DJI",
            "model": "DJI Dock 3",
            "serial_number": "DOCK-A-001",
            "firmware_version": "1.0.0",
        },
        idempotency_key="device-create-001",
        request_meta=RequestMeta("req_device_001", "127.0.0.1"),
    )
    self.assertEqual(replay, first)
    self.assertEqual(self.session.scalar(select(func.count(DeviceModel.id))), 1)

def test_dock_rejects_wrong_device_type(self):
    with self.assertRaises(DomainError) as raised:
        self.service.create_dock(
            actor_id="u_platform_admin",
            tenant_id="t_customer_001",
            values={"device_id": "dev_drone_a"},
            idempotency_key="dock-create-wrong-type",
            request_meta=RequestMeta("req_dock_wrong", None),
        )
    self.assertEqual(raised.exception.code, "MISSION_422")

def test_same_idempotency_key_is_independent_between_target_tenants(self):
    first = self._create_for_tenant("t_customer_001", "SERIAL-A", "shared-key")
    second = self._create_for_tenant("t_customer_002", "SERIAL-B", "shared-key")
    self.assertNotEqual(first["tenant_id"], second["tenant_id"])
```

Add these concrete service tests:

```python
def test_device_update_changes_only_allowed_fields(self):
    result = self.service.update_device(
        actor_id="u_platform_admin",
        tenant_id="t_customer_001",
        device_id="dev_dock_a",
        values={"name": "机场一号更新", "firmware_version": "1.1.0"},
        idempotency_key="device-update-001",
        request_meta=RequestMeta("req_device_update", None),
    )
    self.assertEqual(result["name"], "机场一号更新")
    self.assertEqual(result["firmware_version"], "1.1.0")
    self.assertIsNone(result["status"])

def test_duplicate_serial_returns_mission_422(self):
    with self.assertRaises(DomainError) as raised:
        self._create_for_tenant("t_customer_002", "DOCK-A-001", "duplicate-serial")
    self.assertEqual(raised.exception.code, "MISSION_422")

def test_cross_tenant_dock_association_returns_tenant_404(self):
    with self.assertRaises(DomainError) as raised:
        self.service.create_dock(
            actor_id="u_platform_admin",
            tenant_id="t_customer_001",
            values={
                "device_id": "dev_dock_a",
                "bound_drone_device_id": "dev_drone_b",
            },
            idempotency_key="dock-cross-tenant",
            request_meta=RequestMeta("req_dock_cross", None),
        )
    self.assertEqual(raised.exception.code, "TENANT_404")
```

Add `test_dock_update_changes_binding_and_writes_audit`; assert the returned binding ID, one `dock_updated` audit, the target tenant, and the request ID.

- [ ] **Step 2: Run service tests and verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_device_registry_persistence.DeviceRegistryServiceTests -v
```

Expected: ERROR because `DeviceRegistryService` is missing.

- [ ] **Step 3: Add serializers and service validation helpers**

Add `device_payload()` and `dock_payload()` functions returning JSON-compatible dictionaries. Datetimes must use `.isoformat()` and nullable fields remain `None`.

Add `DeviceRegistryService` with constructor dependencies:

```python
class DeviceRegistryService:
    def __init__(self, session: Session):
        self.session = session
        self.registry = DeviceRegistryRepository(session)
        self.u0 = U0Repository(session)

    def _fingerprint(self, value: dict) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()

    def _typed_device(
        self,
        tenant_id: str,
        device_id: str | None,
        expected_type: str,
        field_name: str,
    ) -> DeviceModel | None:
        if device_id is None:
            return None
        item = self.registry.device(tenant_id, device_id)
        if item.device_type != expected_type:
            raise DomainError(
                "MISSION_422",
                "关联设备类型不符合要求",
                {"field": field_name, "expected_type": expected_type},
            )
        return item
```

- [ ] **Step 4: Implement create and update operations**

Implement `create_device`, `update_device`, `create_dock`, and `update_dock` using these rules:

- IDs are server-generated as `dev_<12 hex>` and `dock_<12 hex>`.
- `create_device` checks global serial uniqueness before insert.
- `update_device` only accepts `name`, `manufacturer`, `model`, and `firmware_version`.
- `create_dock` requires a `DOCK`, optional `DRONE`, and optional `EDGE_NODE`, all in the target tenant.
- `update_dock` only changes `bound_drone_device_id` and `edge_node_device_id`; explicit `None` clears a binding.
- Each operation calls `self.session.flush()`, writes one audit row, and returns a serializer result.
- Wrap each operation with `U0Repository.run_idempotent(tenant_id, method, route_id, key, fingerprint, operation)`.
- Route IDs are `device-create`, `device-update:{device_id}`, `dock-create`, and `dock-update:{dock_id}`.
- Fingerprints include the target tenant, target resource ID when present, and normalized values.
- Audit actions are `device_created`, `device_updated`, `dock_created`, and `dock_updated`.

Do not accept `tenant_id`, `status`, `last_seen_at`, or `environment_json` in service values.

- [ ] **Step 5: Run service and persistence regression tests**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_device_registry_persistence tests.test_u0_persistence -v
```

Expected: PASS; duplicate serial and wrong association types return `MISSION_422`, cross-tenant references return `TENANT_404`, and replays create no duplicate rows or audits.

- [ ] **Step 6: Commit the service layer**

```powershell
git add apps/api/app/device_registry.py tests/test_u1_device_registry_persistence.py
git commit -m "feat: manage idempotent device registry writes"
```

## Task 4: Tenant-Isolated Read APIs and Feature Enforcement

**Files:**
- Modify: `apps/api/app/main.py`
- Create: `tests/test_api_u1_device_registry.py`

- [ ] **Step 1: Write failing read API tests**

Create a temporary migrated database fixture, bootstrap U0, and seed one device and dock per customer tenant. Add tests:

```python
def test_customer_lists_only_own_devices(self):
    response = self.client.get(
        "/api/v1/devices",
        headers={"Authorization": "Bearer demo-customer-a"},
    )
    self.assertEqual(response.status_code, 200)
    self.assertEqual(
        [item["tenant_id"] for item in response.json()["items"]],
        ["t_customer_001"],
    )

def test_cross_tenant_device_detail_returns_tenant_404(self):
    response = self.client.get(
        "/api/v1/devices/dev_customer_b",
        headers={"Authorization": "Bearer demo-customer-a"},
    )
    self.assertEqual(response.status_code, 404)
    self.assertEqual(response.json()["code"], "TENANT_404")

def test_device_read_requires_flight_control(self):
    self._remove_feature("t_customer_001", "FLIGHT_CONTROL")
    response = self.client.get(
        "/api/v1/devices",
        headers={"Authorization": "Bearer demo-customer-a"},
    )
    self.assertEqual(response.status_code, 403)
    self.assertEqual(response.json()["code"], "FEATURE_403")
```

Add these read tests with exact expectations:

```python
def test_platform_reads_selected_customer_tenant(self):
    response = self.client.get(
        "/api/v1/docks",
        headers={
            "Authorization": "Bearer demo-platform",
            "X-Tenant-Id": "t_customer_002",
        },
    )
    self.assertEqual(response.status_code, 200)
    self.assertEqual(
        {item["tenant_id"] for item in response.json()["items"]},
        {"t_customer_002"},
    )

def test_customer_tenant_switch_is_denied(self):
    response = self.client.get(
        "/api/v1/devices",
        headers={
            "Authorization": "Bearer demo-customer-a",
            "X-Tenant-Id": "t_customer_002",
        },
    )
    self.assertEqual(response.status_code, 403)
    self.assertEqual(response.json()["code"], "TENANT_403")
```

Add `test_feature_denial_is_audited` and `test_inaccessible_detail_is_audited`; query `AuditLogModel` after the response and assert action, target service tenant, resource ID, request ID, and denial code.

- [ ] **Step 2: Run API tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_api_u1_device_registry.DeviceRegistryReadApiTests -v
```

Expected: FAIL with HTTP 404 because the four read routes do not exist.

- [ ] **Step 3: Add feature and inaccessible-resource audit helpers**

In `apps/api/app/main.py`, add `_require_feature` that checks `context.has_feature(FeatureCode.FLIGHT_CONTROL)`. On denial it must rollback the request session and call `U0Repository.commit_denial_audit` with action `device_feature_denied`, resource type `feature`, resource ID `FLIGHT_CONTROL`, target service tenant, and `FEATURE_403`.

Add `_commit_registry_denial` that records `device_detail_denied` or `dock_detail_denied` in a separate session after a `TENANT_404`. It must audit the current service tenant and requested resource ID without querying or exposing the actual owner.

Add `_commit_registry_write_denial` for authenticated management requests. It rolls back the request session and uses `commit_denial_audit` with the target service tenant, actor ID, action `device_registry_write_denied`, requested resource ID when present, and the caught domain error code. Pydantic parsing failures occur before a valid business command exists and retain only the unified `MISSION_422` response.

- [ ] **Step 4: Add the four read routes**

Add routes using existing actor, repository, request metadata, and `X-Tenant-Id` dependencies:

```python
@app.get("/api/v1/devices", tags=["U1 飞控平台"])
def list_devices(
    request: Request,
    actor: Actor = Depends(actor_from_authorization),
    repo: U0Repository = Depends(repository),
    meta: RequestMeta = Depends(request_meta),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict:
    context = _resolve_context(request, repo, actor, x_tenant_id, meta)
    _require_feature(request, repo, actor, context, meta)
    registry = DeviceRegistryRepository(repo.session)
    return {"items": [device_payload(item) for item in registry.list_devices(context.tenant_id)]}
```

Implement the detail route with `registry.device(context.tenant_id, device_id)`, catching only `TENANT_404` to commit a denial audit before re-raising. Implement equivalent dock list and detail routes. Lists are ordered by ID and expose no `tenant_id` selector.

- [ ] **Step 5: Run read API tests and existing U0 API tests**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_api_u1_device_registry.DeviceRegistryReadApiTests tests.test_api_u0_app -v
```

Expected: PASS; existing U0 authentication and tenant-switch behavior remains unchanged.

- [ ] **Step 6: Commit read APIs**

```powershell
git add apps/api/app/main.py tests/test_api_u1_device_registry.py
git commit -m "feat: expose tenant-isolated device registry reads"
```

## Task 5: Platform-Only Management APIs and OpenAPI Contract

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_api_u1_device_registry.py`

- [ ] **Step 1: Write failing management API tests**

Add tests covering all four write routes. The primary create test is:

```python
def test_platform_creates_customer_device_with_idempotency(self):
    headers = {
        "Authorization": "Bearer demo-platform",
        "X-Tenant-Id": "t_customer_001",
        "Idempotency-Key": "api-device-create-001",
    }
    payload = {
        "device_type": "DOCK",
        "name": "机场一号",
        "manufacturer": "DJI",
        "model": "DJI Dock 3",
        "serial_number": "DOCK-A-API-001",
        "firmware_version": "1.0.0",
    }
    first = self.client.post("/api/v1/admin/devices", json=payload, headers=headers)
    replay = self.client.post("/api/v1/admin/devices", json=payload, headers=headers)
    self.assertEqual(first.status_code, 200)
    self.assertEqual(replay.json(), first.json())
    self.assertEqual(first.json()["tenant_id"], "t_customer_001")
```

Add named tests with these exact response assertions:

- customer write returns `PERM_403` and a committed denial audit;
- missing or conflicting `Idempotency-Key` returns `IDEMP_409`;
- request bodies containing `tenant_id`, `status`, `last_seen_at`, or `environment_json` return `MISSION_422` because request models forbid extra fields;
- invalid device type returns `MISSION_422`;
- duplicate serial returns `MISSION_422`;
- platform can patch allowed device fields and dock bindings;
- cross-tenant dock association returns `TENANT_404`;
- OpenAPI has all eight paths and each write operation declares `Idempotency-Key`.

For `test_customer_cannot_create_device`, send a valid body as `demo-customer-a`, assert HTTP 403 and `PERM_403`, then query an audit with action `device_admin_write_denied`. For `test_forbidden_fields_use_unified_validation`, send `tenant_id` in a valid create body and assert HTTP 422, `MISSION_422`, and a `details.field_errors` entry whose location ends in `tenant_id`. For `test_openapi_exposes_u1_f02_contract`, assert the exact eight paths listed in the design and find an `Idempotency-Key` header parameter on each `post` and `patch` operation.

- [ ] **Step 2: Run management API tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_api_u1_device_registry.DeviceRegistryWriteApiTests -v
```

Expected: FAIL with HTTP 404 because management routes are absent.

- [ ] **Step 3: Define strict Pydantic request models**

In `apps/api/app/main.py`, import `Literal` and `ConfigDict`. Define models with `model_config = ConfigDict(extra="forbid")`:

```python
class DeviceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_type: Literal["DOCK", "DRONE", "PAYLOAD", "EDGE_NODE"]
    name: str = Field(min_length=1, max_length=255)
    manufacturer: str = Field(min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str = Field(min_length=1, max_length=128)
    firmware_version: str | None = Field(default=None, max_length=128)


class DeviceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    manufacturer: str | None = Field(default=None, min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    firmware_version: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("at least one device field is required")
        for field_name in {"name", "manufacturer"}.intersection(self.model_fields_set):
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class DockCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=64)
    bound_drone_device_id: str | None = Field(default=None, max_length=64)
    edge_node_device_id: str | None = Field(default=None, max_length=64)


class DockUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bound_drone_device_id: str | None = Field(default=None, max_length=64)
    edge_node_device_id: str | None = Field(default=None, max_length=64)
```

Give `DockUpdateRequest` a model validator that rejects an empty `model_fields_set`. The device validator above rejects explicit `null` for `name` and `manufacturer`; `model` and `firmware_version` may be cleared. Use `model_dump(exclude_unset=True)` so explicit `null` clears nullable fields while omitted fields remain unchanged.

- [ ] **Step 4: Add management routes**

Each route must execute in this order:

1. `_resolve_context` from `X-Tenant-Id`.
2. `_require_roles(request, repo, actor, {"PLATFORM_ADMIN"}, meta, action="device_admin_write_denied")`.
3. `_require_feature` for the target service tenant.
4. Call the matching `DeviceRegistryService` method with `actor.id`, `context.tenant_id`, the strict request values, `Idempotency-Key`, and `RequestMeta`.

Use `Header(default=None, alias="Idempotency-Key")` on every write route. Do not accept `tenant_id` as a path, query, or body value.

Wrap only the service call in `try/except DomainError`. On `IDEMP_409`, `MISSION_422`, or `TENANT_404`, call `_commit_registry_write_denial` and re-raise. Do not catch successful responses or convert the original error code.

- [ ] **Step 5: Run API, OpenAPI, and full focused tests**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_api_u1_device_registry tests.test_u1_device_registry_persistence tests.test_api_u0_app -v
```

Expected: PASS with unified `code/message/request_id/details` errors and durable denial audits.

- [ ] **Step 6: Commit management APIs**

```powershell
git add apps/api/app/main.py tests/test_api_u1_device_registry.py
git commit -m "feat: add audited device registry management APIs"
```

## Task 6: Normalized DJI Device Status Synchronization

**Files:**
- Modify: `apps/api/app/device_registry.py`
- Modify: `tests/test_u1_device_registry_persistence.py`

- [ ] **Step 1: Write failing status-service tests**

Use `DjiDock3Simulator` and a registered dock device. Add tests asserting:

```python
def test_device_bound_does_not_claim_device_is_online(self):
    result = self.status_service.apply_event(
        self.bound_event,
        RequestMeta("req_bound_001", "127.0.0.1"),
    )
    self.assertIsNone(result["status"])

def test_device_status_online_updates_last_seen_and_audits_gateway_actor(self):
    result = self.status_service.apply_event(
        FlightEvent(
            event_code="device_status",
            event_time=self.now,
            device_sn="DOCK-A-STATUS-001",
            raw_payload={
                "status": "ONLINE",
                "dock_door": "CLOSED",
                "charging": True,
                "weather": {"wind_speed_mps": 4.2},
                "payload_status": "READY",
            },
        ),
        RequestMeta("req_status_001", "127.0.0.1"),
    )
    self.assertEqual(result["status"], "ONLINE")
    self.assertEqual(result["last_seen_at"], self.now.isoformat())
    self.assertEqual(self._latest_audit().actor, "dji_gateway")
    self.assertEqual(self._latest_audit().request_id, "req_status_001")
```

Add these status tests:

```python
def test_offline_preserves_last_seen(self):
    self._apply_online()
    previous = self.repository.device_by_serial("DOCK-A-STATUS-001").last_seen_at
    result = self.status_service.apply_event(
        FlightEvent(
            event_code="device_status",
            event_time=self.now + timedelta(seconds=5),
            device_sn="DOCK-A-STATUS-001",
            raw_payload={"status": "OFFLINE", "ignored": "raw"},
        ),
        RequestMeta("req_status_offline", None),
    )
    self.assertEqual(result["status"], "OFFLINE")
    self.assertEqual(result["last_seen_at"], previous.isoformat())

def test_invalid_status_returns_dji_502(self):
    with self.assertRaises(DomainError) as raised:
        self.status_service.apply_event(
            FlightEvent(
                event_code="device_status",
                event_time=self.now,
                device_sn="DOCK-A-STATUS-001",
                raw_payload={"status": "UNKNOWN"},
            ),
            RequestMeta("req_status_invalid", None),
        )
    self.assertEqual(raised.exception.code, "DJI_502")
```

Add `test_unknown_serial_returns_tenant_404` and `test_environment_snapshot_uses_allowlist`; the latter asserts the stored JSON contains exactly `dock_door`, `charging`, `weather`, and `payload_status` when the raw payload also includes an ignored key.

- [ ] **Step 2: Run status tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_device_registry_persistence.DeviceStatusServiceTests -v
```

Expected: ERROR because `DeviceStatusService` is missing.

- [ ] **Step 3: Implement the status service**

Add:

```python
class DeviceStatusService:
    ENVIRONMENT_KEYS = {
        "dock_door",
        "charging",
        "weather",
        "payload_status",
    }

    def __init__(self, session: Session):
        self.session = session
        self.registry = DeviceRegistryRepository(session)
        self.u0 = U0Repository(session)

    def apply_event(self, event: FlightEvent, request_meta: RequestMeta) -> dict:
        device = self.registry.device_by_serial(event.device_sn)
        if event.event_code == "device_bound":
            return device_payload(device)
        if event.event_code != "device_status":
            return device_payload(device)

        status = event.raw_payload.get("status")
        if status not in {"ONLINE", "OFFLINE"}:
            raise DomainError(
                "DJI_502",
                "DJI 设备状态格式错误",
                {"field": "raw_payload.status"},
            )
        before_status = device.status
        device.status = status
        if status == "ONLINE":
            device.last_seen_at = event.event_time
        device.updated_at = utc_now()

        dock = self.session.scalar(
            select(DockModel).where(
                DockModel.tenant_id == device.tenant_id,
                DockModel.device_id == device.id,
            )
        )
        if dock is not None:
            environment = dict(dock.environment_json)
            environment.update(
                {
                    key: event.raw_payload[key]
                    for key in self.ENVIRONMENT_KEYS
                    if key in event.raw_payload
                }
            )
            dock.environment_json = environment
            dock.updated_at = utc_now()

        self.u0.audit(
            tenant_id=device.tenant_id,
            actor="dji_gateway",
            action="device_status_synced",
            resource_type="device",
            resource_id=device.id,
            request_meta=request_meta,
            before_status=before_status,
            after_status=status,
        )
        self.session.commit()
        return device_payload(device)
```

Do not treat `device_bound`, telemetry, low battery, or media callbacks as online evidence.

- [ ] **Step 4: Run U1 status, gateway, and persistence tests**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_device_registry_persistence.DeviceStatusServiceTests tests.test_u1_dji_gateway_contract tests.test_u1_flight -v
```

Expected: PASS; U1-F01 behavior remains unchanged.

- [ ] **Step 5: Commit status synchronization**

```powershell
git add apps/api/app/device_registry.py tests/test_u1_device_registry_persistence.py
git commit -m "feat: synchronize normalized DJI device status"
```

## Task 7: Documentation, Full Regression, PostgreSQL Smoke, and Remote Sync

**Files:**
- Create: `scripts/test_postgres_migrations.sh`
- Modify: `docs/60-test-reports/U1-flight-test-report.md`

- [ ] **Step 1: Run complete local verification**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -m compileall -q src apps/api/app
git diff --check
```

Expected: all tests pass, compilation exits 0, and `git diff --check` prints nothing.

- [ ] **Step 2: Add the Linux PostgreSQL migration smoke script**

Create `scripts/test_postgres_migrations.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$project_root/infra/compose/docker-compose.persistence-test.yml"
python_bin="${PYTHON:-$project_root/.venv/bin/python}"
project_name="drone-u1-f02-persistence-test"
port="${U0_POSTGRES_TEST_PORT:-55432}"

command -v docker >/dev/null
test -x "$python_bin"

cleanup() {
  docker compose -p "$project_name" -f "$compose_file" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

export U0_POSTGRES_TEST_PORT="$port"
export DATABASE_URL="postgresql+psycopg://u0_test:u0_test@127.0.0.1:$port/drone_u0_test"
export PYTHONPATH="$project_root/apps/api:$project_root/src"

docker compose -p "$project_name" -f "$compose_file" up -d --wait postgres
"$python_bin" -m alembic upgrade head
"$python_bin" -m alembic downgrade base
"$python_bin" -m alembic upgrade head
"$python_bin" - <<'PY'
import os
from sqlalchemy import create_engine, inspect
from app.models import Base

engine = create_engine(os.environ["DATABASE_URL"])
try:
    actual = set(inspect(engine).get_table_names())
    expected = set(Base.metadata.tables) | {"alembic_version"}
    if actual != expected:
        raise SystemExit(
            f"table mismatch: expected={sorted(expected)}, actual={sorted(actual)}"
        )
finally:
    engine.dispose()
PY
echo "PostgreSQL migration smoke test passed."
```

Mark it executable with `git update-index --add --chmod=+x scripts/test_postgres_migrations.sh`. Run `bash -n scripts/test_postgres_migrations.sh`; expected exit code is 0.

- [ ] **Step 3: Push the current branch for cloud verification**

```powershell
git add scripts/test_postgres_migrations.sh
git commit -m "test: add Linux PostgreSQL migration smoke script"
git -c http.proxy=http://127.0.0.1:7897 push -u origin codex/u1-f02-device-registry
```

Expected: branch push succeeds. This is an intermediate verification push, not a merge.

- [ ] **Step 4: Run PostgreSQL migration smoke in the established cloud Docker environment**

First verify the SSH host key for `8.163.127.126` against the cloud console or previously approved fingerprint. Do not use `StrictHostKeyChecking=no` and do not replace a changed key without human confirmation.

After the host identity is trusted, update or clone the feature branch into a dedicated test directory, install `apps/api/requirements.txt` into its `.venv`, and run:

```bash
test -d /opt/drone-u1-f02-migration-test/.git || git clone --branch codex/u1-f02-device-registry https://github.com/baoyongqiang77-cell/-.git /opt/drone-u1-f02-migration-test
cd /opt/drone-u1-f02-migration-test
git fetch origin codex/u1-f02-device-registry
git checkout codex/u1-f02-device-registry
git merge --ff-only origin/codex/u1-f02-device-registry
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.txt
./scripts/test_postgres_migrations.sh
```

Expected: `upgrade head -> downgrade base -> upgrade head` exits 0, final revision is `20260621_0002`, and inspection contains ten business tables plus `alembic_version`. Keep PostgreSQL bound to loopback and remove only the script-owned Compose project afterward.

- [ ] **Step 5: Update U1 acceptance evidence**

Add U1-F02 scope and actual measured results to `docs/60-test-reports/U1-flight-test-report.md`. Record:

- tenant-filtered device and dock reads;
- platform-only audited writes;
- target-tenant idempotency;
- database-level composite tenant foreign keys;
- normalized `ONLINE/OFFLINE` synchronization and binding-not-online behavior;
- final focused/full test counts and PostgreSQL migration result;
- no real DJI device, credential, Cloud API, aircraft-model, or payload-model acceptance claim.

- [ ] **Step 6: Commit verification evidence**

```powershell
git add docs/60-test-reports/U1-flight-test-report.md
git commit -m "docs: record U1-F02 device registry verification"
```

- [ ] **Step 7: Perform final review and verification**

Run:

```powershell
git diff origin/main...HEAD --stat
git diff --check origin/main...HEAD
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests
git status --short
```

Expected: only U1-F02 design, plan, implementation, tests, migration, and U1 report changes are present; all tests pass; worktree is clean after commits.

- [ ] **Step 8: Push the final feature branch**

```powershell
git -c http.proxy=http://127.0.0.1:7897 push -u origin codex/u1-f02-device-registry
git rev-list --left-right --count origin/codex/u1-f02-device-registry...HEAD
```

Expected: push succeeds and divergence is `0 0`. Stop at the pushed feature branch for review; do not merge to `main` without explicit approval.
