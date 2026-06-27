# U1-F07 Mission Dispatch Design

U1-F07 adds tenant-scoped mission dispatch to the existing DJI Dock 3 adapter boundary. It dispatches only approved missions, records the gateway receipt, and updates mission state based on the adapter response. It does not call DJI Cloud API directly, does not prove a real flight executed, and does not create telemetry or `flight_events`.

## Scope

- Add `mission_dispatch_receipts` persistence with `tenant_id`, `mission_id`, `device_id`, `route_version_id`, `operation`, `accepted`, `external_request_id`, `gateway_mode`, `raw_payload`, and timestamps.
- Add `POST /api/v1/missions/{mission_id}/dispatch`.
- Require `APPROVED` status before dispatch. The service first transitions the mission to `DISPATCHING`.
- Build `DispatchMissionCommand` from tenant, request id, idempotency key, device serial number, mission id, and route version id.
- Call a `DjiGateway` implementation through the adapter contract. The current API app uses `DjiDock3Simulator`.
- If the receipt is accepted, transition `DISPATCHING -> DISPATCHED`. If the gateway returns a non-accepted receipt, transition `DISPATCHING -> DISPATCH_FAILED`.
- If the gateway raises `DJI_502`, rollback the service transaction and write denial audit through the existing write-denial path.

## API And Security

- Endpoint: `POST /api/v1/missions/{mission_id}/dispatch`
- Body: optional `dispatch_note`
- Headers: `Authorization`, `Idempotency-Key`, optional controlled `X-Tenant-Id`
- Feature: `FLIGHT_CONTROL`
- Idempotency route scope is mission-specific, so replaying the same dispatch request returns the same receipt payload.

Customers can dispatch only their own approved missions. Platform operators may use the existing controlled tenant switch. Cross-tenant access returns `TENANT_404` without resource disclosure.

## State And Audit

Valid success path:

1. `APPROVED -> DISPATCHING`
2. Gateway dispatch call
3. `DISPATCHING -> DISPATCHED`

Failure receipt path:

1. `APPROVED -> DISPATCHING`
2. Gateway dispatch call
3. `DISPATCHING -> DISPATCH_FAILED`

Invalid status returns `STATE_409`. Successful accepted dispatch writes `mission_dispatched`; non-accepted dispatch writes `mission_dispatch_failed`. The audit record stores before and after mission status.

## Boundary

This unit uses the existing gateway contract and simulator. `raw_payload.execution_proof = SIMULATED_ONLY` remains a development-only receipt marker. Real DJI Cloud API credentials, route upload, device execution proof, telemetry WebSocket, return-to-home safety logic, and `flight_events` persistence remain later or pending-confirmation work.
