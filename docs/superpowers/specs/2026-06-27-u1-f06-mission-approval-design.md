# U1-F06 Mission Approval Design

U1-F06 adds the tenant-scoped approval step after mission creation. It covers submitting a `DRAFT` mission for approval, recording approval evidence, and completing the built-in approval flow as `APPROVED` or `REJECTED`. It does not integrate a real OA or airspace approval system, does not dispatch to DJI, and does not claim production approval readiness.

## Scope

- Add `mission_approvals` persistence with `tenant_id`, `mission_id`, `external_system`, `external_id`, `status`, `callback_payload`, `submitted_by`, `decided_by`, `decision_comment`, and timestamps.
- Add `POST /api/v1/missions/{id}/submit-approval` to move a mission from `DRAFT` to `PENDING_APPROVAL`.
- Add built-in approval decision endpoints for approve and reject. These move a mission from `PENDING_APPROVAL` to `APPROVED` or `REJECTED`.
- Keep all approval writes tenant-scoped, `FLIGHT_CONTROL` gated, idempotent, audited, and protected by the documented mission state machine.
- Store external approval identifiers and callback payloads as trace fields only. OA/airspace protocol, signing, callback schema, attachment storage, and production routing remain pending confirmation.

## API

- `POST /api/v1/missions/{mission_id}/submit-approval`
  - Body: `external_system`, `external_id`, `callback_payload`, `comment`.
  - Creates one approval record and sets mission status to `PENDING_APPROVAL`.
- `POST /api/v1/missions/{mission_id}/approvals/{approval_id}/approve`
  - Body: `external_status`, `external_id`, `callback_payload`, `comment`.
  - Sets approval status to `APPROVED` and mission status to `APPROVED`.
- `POST /api/v1/missions/{mission_id}/approvals/{approval_id}/reject`
  - Body: same shape as approve.
  - Sets approval status to `REJECTED` and mission status to `REJECTED`.

All three endpoints require `Idempotency-Key`. Customers can operate only on their tenant. Platform operators may use controlled `X-Tenant-Id` through the existing context resolver.

## State And Errors

- Valid transitions are enforced through the existing documented mission state machine:
  - `DRAFT -> PENDING_APPROVAL`
  - `PENDING_APPROVAL -> APPROVED`
  - `PENDING_APPROVAL -> REJECTED`
- Invalid status transitions return `STATE_409`.
- Missing or invisible missions and approvals return `TENANT_404`.
- Invalid approval payloads return `MISSION_422`.
- Idempotency conflicts return `IDEMP_409`.

## Audit And Boundary

Successful writes record `mission_approval_submitted`, `mission_approved`, or `mission_rejected` with before and after statuses. Denied approval writes use the existing `mission_write_denied` audit path. This unit does not call DJI, does not create `flight_events`, and does not evaluate real weather, airspace, OA, or external attachment evidence.
