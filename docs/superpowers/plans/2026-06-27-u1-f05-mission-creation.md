# U1-F05 Mission Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tenant-scoped flight mission creation with DRAFT status and validation against existing U1 registries.

**Architecture:** Add `missions` persistence, a focused `mission_management.py` service/repository, FastAPI create/read endpoints, and TDD tests mirroring U1-F02 through U1-F04 patterns.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, Python unittest.

---

### Task 1: Persistence

- [ ] Write failing tests for `MissionModel`, migration round trip, status constraint, and same-tenant foreign keys.
- [ ] Add `MissionModel` and Alembic migration `20260627_0005_u1_mission_creation.py`.
- [ ] Run persistence tests until green.

### Task 2: Service

- [ ] Write failing tests for idempotent customer mission creation, route-version validation, device/dock validation, inspection target validation, and DRAFT status.
- [ ] Implement `MissionRepository`, serializers, `MissionManagementService`, validation, and audit.
- [ ] Run service tests until green.

### Task 3: API

- [ ] Write failing API tests for POST/list/detail, customer create, feature denial, cross-tenant denial audit, idempotency, invalid payloads, and OpenAPI paths.
- [ ] Add Pydantic models and FastAPI routes, update expected DB revision.
- [ ] Run API tests until green.

### Task 4: Verification

- [ ] Update U1 test report.
- [ ] Run focused tests, full tests, compileall, `git diff --check`, migration script syntax check.
- [ ] Commit, push, create PR.
