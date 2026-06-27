# U1-F08 Telemetry Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tenant-scoped telemetry event persistence and a minimal mission telemetry WebSocket snapshot.

**Architecture:** Add `FlightEventModel` and a focused telemetry service that persists normalized gateway events. REST endpoints reuse existing tenant, feature, idempotency, and audit helpers; WebSocket uses the same bearer token and tenant checks with a short snapshot response.

**Tech Stack:** FastAPI REST/WebSocket, SQLAlchemy ORM, Alembic, unittest, existing DJI gateway `FlightEvent` contract.

---

### Task 1: Flight Event Persistence

**Files:**
- Modify: `apps/api/app/models.py`
- Create: `alembic/versions/20260627_0008_u1_flight_events.py`
- Modify: `tests/test_u0_persistence.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [x] Add failing metadata and Alembic tests for `flight_events`.
- [x] Add `FlightEventModel` with tenant-scoped mission FK and fixed outer event payload columns.
- [x] Add Alembic revision `20260627_0008`.
- [x] Run focused persistence tests.

### Task 2: Telemetry Service

**Files:**
- Create: `apps/api/app/telemetry_events.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [x] Add failing service tests for event ingestion, tenant isolation, idempotent replay, and audit.
- [x] Implement event persistence from normalized `FlightEvent`.
- [x] Implement list serialization for mission telemetry events.
- [x] Run focused service tests.

### Task 3: REST And WebSocket API

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_api_u1_mission_creation.py`

- [x] Add failing API tests for telemetry ingestion, list, WebSocket snapshot, cross-tenant denial, and OpenAPI path.
- [x] Add REST request model and endpoints.
- [x] Add WebSocket endpoint with header-based bearer auth and tenant checks.
- [x] Bump expected database revision to `20260627_0008`.
- [x] Run focused API tests.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/60-test-reports/U1-flight-test-report.md`

- [x] Update U1 report with U1-F08 evidence and limitations.
- [x] Run compile, migration script syntax check, diff check, focused tests, U0 persistence tests, and full unittest discovery.
- [x] Commit, push branch, and create a PR after verification passes.
