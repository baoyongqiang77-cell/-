# U1-F06 Mission Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the U1-F06 tenant-scoped mission approval flow from `DRAFT` to `PENDING_APPROVAL`, then to `APPROVED` or `REJECTED`.

**Architecture:** Extend the existing mission management service with approval persistence and state transition methods. Reuse current API context resolution, `FLIGHT_CONTROL` checks, idempotency, unified errors, and audit commit behavior.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy ORM, Alembic, unittest, SQLite migration tests.

---

### Task 1: Approval Persistence

**Files:**
- Modify: `apps/api/app/models.py`
- Create: `alembic/versions/20260627_0006_u1_mission_approval.py`
- Modify: `tests/test_u0_persistence.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [ ] Add failing tests that require `mission_approvals` metadata, constraints, and Alembic upgrade/downgrade support.
- [ ] Add `MissionApprovalModel` with tenant-scoped mission foreign key and fixed approval statuses.
- [ ] Add Alembic revision `20260627_0006` after `20260627_0005`.
- [ ] Run focused persistence tests and confirm they pass.

### Task 2: Approval Service

**Files:**
- Modify: `apps/api/app/mission_management.py`
- Modify: `tests/test_u1_mission_creation_persistence.py`

- [ ] Add failing tests for submit, approve, reject, invalid state, cross-tenant approval, idempotent replay, and audit records.
- [ ] Add `approval_payload`, approval repository methods, and service methods.
- [ ] Use `MissionStateMachine.ALLOWED` to enforce documented transitions.
- [ ] Run focused service tests and confirm they pass.

### Task 3: Approval API

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_api_u1_mission_creation.py`

- [ ] Add failing API tests for submit, approve, reject, missing idempotency key, unauthorized feature, OpenAPI paths, and cross-tenant non-disclosure.
- [ ] Add request models and three approval endpoints.
- [ ] Bump expected database revision to `20260627_0006`.
- [ ] Run focused API tests and confirm they pass.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/60-test-reports/U1-flight-test-report.md`

- [ ] Update U1 test report to include U1-F06 and preserve pending OA/airspace boundary.
- [ ] Run compile, migration script syntax check, diff check, focused tests, and full unittest discovery.
- [ ] Commit, push branch, and create a PR after verification passes.
