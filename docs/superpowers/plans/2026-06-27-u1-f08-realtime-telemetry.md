# U1-F08 Realtime Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade U1-F08 telemetry WebSocket from snapshot-only to simulator-backed realtime fan-out.

**Architecture:** Add a small in-process `TelemetryHub` keyed by `(tenant_id, mission_id)`. WebSocket connections subscribe after tenant and feature checks, receive a typed snapshot, then receive typed event messages after REST telemetry ingestion succeeds.

**Tech Stack:** FastAPI WebSocket, standard-library thread-safe queues, SQLAlchemy-backed telemetry service, unittest/TestClient.

---

### Task 1: Red Tests For Realtime WebSocket

**Files:**
- Modify: `tests/test_api_u1_mission_creation.py`

- [x] Add failing tests for typed snapshot, hub event delivery, telemetry POST broadcast, and `FEATURE_403` WebSocket denial.
- [x] Run focused tests and confirm failures are caused by missing realtime behavior/message shape.

### Task 2: Minimal Telemetry Hub

**Files:**
- Create: `apps/api/app/telemetry_hub.py`
- Modify: `apps/api/app/main.py`

- [x] Add `TelemetryHub` with `subscribe`, `unsubscribe`, and `broadcast` methods.
- [x] Store the hub on `app.state.telemetry_hub` during `create_app`.
- [x] Keep subscriptions keyed by tenant and mission to prevent cross-tenant broadcasts.

### Task 3: WebSocket And Broadcast Wiring

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `tests/test_api_u1_mission_creation.py`

- [x] Change the WebSocket success message to `{"type": "snapshot", "mission_id": ..., "items": ...}`.
- [x] Keep the WebSocket open and forward hub events until disconnect.
- [x] After telemetry REST write succeeds, broadcast `{"type": "event", "mission_id": ..., "item": ...}`.
- [x] Ensure error paths still send unified error shape and close.
- [x] Run focused API tests and confirm green.

### Task 4: Docs And Verification

**Files:**
- Modify: `docs/60-test-reports/U1-flight-test-report.md`
- Modify: `docs/superpowers/plans/2026-06-27-u1-f08-realtime-telemetry.md`

- [x] Update U1 report to say U1-F08 now includes simulator realtime fan-out, still not real DJI production telemetry.
- [x] Run compile, `git diff --check`, U1 focused tests, U0 persistence tests, and full unittest discovery.
- [x] Commit, push the branch, and update PR #9.
