# U1-F07 Mission Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tenant-scoped mission dispatch from `APPROVED` through the DJI gateway adapter to `DISPATCHED` or `DISPATCH_FAILED`.

**Architecture:** Extend mission management with a dispatch receipt model and service method. The service uses existing mission state rules, U0 idempotency/audit, and the `DjiGateway` protocol; the API injects `DjiDock3Simulator` for this increment.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy ORM, Alembic, unittest, existing DJI gateway simulator.

---

### Task 1: Dispatch Persistence

**Files:**
- Modify: `apps/api/app/models.py`
- Create: `alembic/versions/20260627_0007_u1_mission_dispatch.py`
- Modify: `tests/test_u0_persistence.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [ ] Add failing tests requiring `mission_dispatch_receipts` metadata and Alembic upgrade/downgrade support.
- [ ] Add `MissionDispatchReceiptModel` with tenant-scoped mission FK and gateway receipt fields.
- [ ] Add Alembic revision `20260627_0007` after `20260627_0006`.
- [ ] Run focused persistence tests and confirm they pass.

### Task 2: Dispatch Service

**Files:**
- Modify: `apps/api/app/mission_management.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [ ] Add failing tests for approved dispatch success, invalid state, cross-tenant mission, idempotent replay, gateway failure, and audit.
- [ ] Implement `dispatch_mission` using `DispatchMissionCommand` and a `DjiGateway` instance.
- [ ] Persist gateway receipts and update mission status from `APPROVED` to `DISPATCHING` then `DISPATCHED` or `DISPATCH_FAILED`.
- [ ] Run focused service tests and confirm they pass.

### Task 3: Dispatch API

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_api_u1_mission_creation.py`

- [ ] Add failing API tests for dispatch success, missing idempotency key, feature denial, cross-tenant non-disclosure, invalid state, and OpenAPI path.
- [ ] Add dispatch request model and `POST /api/v1/missions/{mission_id}/dispatch`.
- [ ] Bump expected database revision to `20260627_0007`.
- [ ] Run focused API tests and confirm they pass.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/60-test-reports/U1-flight-test-report.md`

- [ ] Update U1 report to include U1-F07 and preserve DJI simulator boundary.
- [ ] Run compile, migration script syntax check, diff check, focused tests, and full unittest discovery.
- [ ] Commit, push branch, and create a PR after verification passes.
