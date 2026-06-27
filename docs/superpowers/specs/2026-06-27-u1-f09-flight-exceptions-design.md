# U1-F09 Flight Exceptions Design

U1-F09 adds a tenant-scoped flight exception linkage path on top of U1-F08 `flight_events`. It converts selected simulator or normalized flight events into platform-side flight exception records so operations users can see abnormal flight conditions before the later U2 alert/work-order pipeline is connected.

## Scope

- Add `flight_exception_links` persistence for U1 flight-control exceptions.
- Link one abnormal `flight_event` to at most one flight exception record.
- Support an explicit link API:
  - `POST /api/v1/missions/{mission_id}/flight-events/{flight_event_id}/link-exception`
  - `GET /api/v1/missions/{mission_id}/flight-exceptions`
- Require the same bearer token, tenant context, `FLIGHT_CONTROL`, and write idempotency rules used by U1 mission telemetry.
- Write audit action `flight_exception_linked` after successful linkage.
- Keep this as a U1 flight-control abnormal event record, not a U2 visual-analysis `events/work_orders` record.

## Exception Mapping

The first increment recognizes these simulator or normalized event codes:

| flight_event.event_code | exception_code | severity |
| --- | --- | --- |
| `low_battery` | `LOW_BATTERY` | `HIGH` |
| `device_unresponsive` | `DEVICE_UNRESPONSIVE` | `HIGH` |
| `lost_link` | `LOST_LINK` | `CRITICAL` |
| `timeout` | `TIMEOUT` | `MEDIUM` |

Unknown event codes return `MISSION_422` and are not linked. Future increments may add media/checksum-related mappings after media sync boundaries are implemented.

## Data Model

`flight_exception_links` fields:

- `id`
- `tenant_id`
- `mission_id`
- `flight_event_id`
- `device_id`
- `exception_code`
- `severity`
- `status`
- `payload_json`
- `created_at`
- `updated_at`

Constraints:

- `tenant_id` references `tenants.id`.
- `(tenant_id, mission_id)` references `missions`.
- `flight_event_id` references `flight_events.id`.
- `(tenant_id, flight_event_id)` is unique so the same flight event cannot create duplicate exception records.
- `status` uses `OPEN`, `ACKNOWLEDGED`, `CLOSED`.
- `severity` uses `MEDIUM`, `HIGH`, `CRITICAL`.

`payload_json` stores the source `flight_event` payload and mapping metadata. It does not claim real DJI abnormal-event evidence.

## API Behavior

`POST /api/v1/missions/{mission_id}/flight-events/{flight_event_id}/link-exception`

- Requires `Idempotency-Key`.
- Resolves tenant context and checks `FLIGHT_CONTROL`.
- Verifies mission and flight event both belong to the resolved tenant.
- Verifies the flight event belongs to the mission path parameter.
- Creates a flight exception link with `status = OPEN`.
- Replays the same response on idempotent retry.
- Returns `TENANT_404` for cross-tenant mission or event access.
- Returns `MISSION_422` for unsupported event codes or event/mission mismatch.

`GET /api/v1/missions/{mission_id}/flight-exceptions`

- Resolves tenant context and checks `FLIGHT_CONTROL`.
- Returns only exception links for the resolved tenant and requested mission.
- Returns `TENANT_404` when the mission is not visible to the caller.

## Security And Boundary

- Customer tenants can only link and list exceptions for their own missions.
- Platform operators may use controlled tenant switching with `X-Tenant-Id`.
- This increment does not create U2 visual-analysis `events`, `event_asset_links`, `review_records`, `feedback_samples`, or `work_orders`.
- This increment does not call real DJI Cloud API, does not subscribe to real DJI abnormal-event topics, and does not prove production abnormal-event integration.
- This increment does not update the mission state machine from exception payloads. Mission state changes remain governed by explicit mission APIs, DJI gateway receipts, or later approved state-transition logic.

## Tests

- Persistence tests cover table metadata, Alembic upgrade/downgrade, unique `tenant_id + flight_event_id`, fixed severity/status constraints, and required tenant-scoped FKs.
- Service tests cover successful low-battery linkage, idempotent replay, duplicate source event rejection/replay, unsupported event rejection, cross-tenant mission/event denial, and audit creation.
- API tests cover POST linkage, GET list, missing `Idempotency-Key`, cross-tenant `TENANT_404`, unsupported event `MISSION_422`, and `FEATURE_403` when `FLIGHT_CONTROL` is removed.
- Full project verification must keep U0 persistence, U1 focused tests, and full unittest discovery green.
