# U1-F04 Route Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tenant-scoped route and route-version management for U1 flight control.

**Architecture:** Add `routes` and `route_versions` persistence, a focused `route_management.py` service/repository, FastAPI read/admin endpoints, and tests mirroring the U1-F02/U1-F03 patterns. Writes are platform-admin-only, idempotent, audited, and bound to `FLIGHT_CONTROL`.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite/PostgreSQL-compatible migrations, Python unittest.

---

### Task 1: Persistence

**Files:**
- Modify: `apps/api/app/models.py`
- Create: `alembic/versions/20260627_0004_u1_route_management.py`
- Test: `tests/test_u1_route_management_persistence.py`

- [ ] Write failing metadata and migration tests for `routes` and `route_versions`.
- [ ] Run the focused persistence tests and confirm they fail because the models/tables do not exist.
- [ ] Add SQLAlchemy models and Alembic migration with tenant foreign keys, same-tenant route/version uniqueness, route format/checksum constraints, and downgrade.
- [ ] Run focused persistence tests and confirm they pass.
- [ ] Commit persistence changes.

### Task 2: Service And Validation

**Files:**
- Create: `apps/api/app/route_management.py`
- Test: `tests/test_u1_route_management_persistence.py`

- [ ] Write failing service tests for tenant filtering, idempotent route creation, route version creation, asset binding validation, duplicate version rejection, and invalid geometry/checksum.
- [ ] Run focused service tests and confirm expected failures.
- [ ] Implement `RouteRepository`, payload serializers, `RouteManagementService`, normalization, duplicate checks, asset binding validation against U1-F03 asset tables, and audits.
- [ ] Run focused service tests and confirm they pass.
- [ ] Commit service changes.

### Task 3: API

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `tests/test_api_u1_route_management.py`

- [ ] Write failing API tests for route list/detail/version reads, cross-tenant denial audit, feature denial, platform-admin writes, customer write denial, idempotency conflict, validation errors, and OpenAPI paths.
- [ ] Run focused API tests and confirm expected failures.
- [ ] Add Pydantic request models, route read endpoints, route admin write endpoints, read/write helper functions, and update expected DB revision.
- [ ] Run focused API tests and confirm they pass.
- [ ] Commit API changes.

### Task 4: Verification And Delivery

**Files:**
- Modify: `docs/60-test-reports/U1-flight-test-report.md`

- [ ] Update U1 report with U1-F04 evidence and explicit boundaries.
- [ ] Run `python -m unittest tests.test_u1_route_management_persistence tests.test_api_u1_route_management -v`.
- [ ] Run full test suite.
- [ ] Run `python -m compileall -q src apps/api/app`.
- [ ] Run `git diff --check`.
- [ ] Push branch and create PR.
