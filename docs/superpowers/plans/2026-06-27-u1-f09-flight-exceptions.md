# U1-F09 Flight Exceptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tenant-scoped U1 flight exception linkage path from abnormal `flight_events`.

**Architecture:** Add `flight_exception_links` persistence and a focused service that maps selected `flight_events` to U1 flight-control exception records. REST endpoints reuse existing mission tenant, feature, idempotency, and audit helpers; this increment does not create U2 visual-analysis events or work orders.

**Tech Stack:** FastAPI REST, SQLAlchemy ORM, Alembic, unittest, existing U1 telemetry event service/model.

---

### Task 1: Persistence And Migration

**Files:**
- Modify: `apps/api/app/models.py`
- Create: `alembic/versions/20260627_0009_u1_flight_exceptions.py`
- Modify: `tests/test_u0_persistence.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [x] Add failing metadata and Alembic tests for `flight_exception_links`.
- [x] Add `FlightExceptionLinkModel` with tenant-scoped mission FK, `flight_event_id`, `device_id`, `exception_code`, `severity`, `status`, `payload_json`, timestamps, and constraints.
- [x] Add Alembic revision `20260627_0009` after `20260627_0008`.
- [x] Bump API expected database revision to `20260627_0009`.
- [x] Run focused persistence tests and confirm green.

### Task 2: Exception Link Service

**Files:**
- Create: `apps/api/app/flight_exceptions.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [x] Add failing service tests for low-battery linkage, idempotent replay, unsupported event `MISSION_422`, cross-tenant denial, and audit creation.
- [x] Implement fixed mapping: `low_battery -> LOW_BATTERY/HIGH`, `device_unresponsive -> DEVICE_UNRESPONSIVE/HIGH`, `lost_link -> LOST_LINK/CRITICAL`, `timeout -> TIMEOUT/MEDIUM`.
- [x] Implement `link_exception(...)` with tenant validation, same-mission validation, duplicate source-event protection, idempotency, and audit.
- [x] Implement `list_exceptions(tenant_id, mission_id)`.
- [x] Run focused service tests and confirm green.

### Task 3: REST API

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_api_u1_mission_creation.py`

- [x] Add failing API tests for POST link, GET list, missing `Idempotency-Key`, unsupported event `MISSION_422`, cross-tenant `TENANT_404`, and `FEATURE_403`.
- [x] Add `POST /api/v1/missions/{mission_id}/flight-events/{flight_event_id}/link-exception`.
- [x] Add `GET /api/v1/missions/{mission_id}/flight-exceptions`.
- [x] Expose both paths in OpenAPI.
- [x] Run focused API tests and confirm green.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/60-test-reports/U1-flight-test-report.md`
- Modify: `docs/superpowers/plans/2026-06-27-u1-f09-flight-exceptions.md`

- [x] Update U1 report with U1-F09 evidence and limitations.
- [x] Run `compileall`, migration script syntax check, `git diff --check`, U1 focused tests, U0 persistence tests, and full unittest discovery.
- [x] Commit, push branch, and create PR after verification passes.
