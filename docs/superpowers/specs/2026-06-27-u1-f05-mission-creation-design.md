# U1-F05 Mission Creation Design

## Scope

U1-F05 adds tenant-scoped flight mission creation. A mission selects a route version, a device or dock, a planned schedule time, inspection targets, and media policy. Created missions start in `DRAFT`; no approval, DJI dispatch, telemetry, media sync, or device-side execution is performed in this unit.

## Data Model

`missions` stores `tenant_id`, `route_id`, `route_version_id`, `device_id`, optional `dock_id`, `status`, `schedule_time`, `inspection_targets`, `media_policy`, and timestamps. The table enforces documented mission statuses and same-tenant relationships to `routes`, `route_versions`, `devices`, and `docks`.

## API

- `POST /api/v1/missions`: create a `DRAFT` mission. Available to tenants with `FLIGHT_CONTROL`; supports customer tenant creation within its own tenant and platform controlled tenant switching.
- `GET /api/v1/missions`: list missions in current tenant.
- `GET /api/v1/missions/{mission_id}`: read mission details in current tenant.

Writes require `Idempotency-Key`, reject client-supplied `tenant_id/status`, and audit success and denial.

## Validation

Mission creation validates:

- route version belongs to the same route and tenant.
- device belongs to the same tenant and is `DOCK` or `DRONE`.
- optional dock belongs to the same tenant.
- inspection targets are same-tenant `road`, `bridge`, or `slope` assets.
- media policy is an object and at least one of `video` or `image_interval_sec` is requested.
- initial status is always `DRAFT`.

Invalid mission parameters return `MISSION_422`; cross-tenant invisible resources return `TENANT_404`; missing feature authorization returns `FEATURE_403`.

## Boundaries

This unit does not submit approval, call OA/airspace systems, dispatch to DJI, verify weather, upload routes, open telemetry WebSocket, create flight events, or claim real flight readiness.
