# U1-F08 Telemetry Events Design

U1-F08 adds tenant-scoped telemetry event persistence and a minimal WebSocket snapshot subscription for mission telemetry. It stores normalized gateway `FlightEvent` payloads in `flight_events`, lets tests inject simulator telemetry through the business API boundary, and lets authorized users subscribe to a mission's current telemetry event list. It does not connect to real DJI Cloud API, does not implement a production MQTT/WebSocket bridge, and does not claim 1-second real device telemetry.

## Scope

- Add `flight_events` persistence with `tenant_id`, `mission_id`, `device_id`, `event_code`, `event_time`, `device_sn`, `payload_json`, and timestamps.
- Add a service method that accepts a normalized `FlightEvent`, validates mission and device tenant ownership, and persists the exact outer payload shape. This increment records telemetry only; it does not drive mission state transitions.
- Add `POST /api/v1/missions/{mission_id}/telemetry-events` for simulator-backed event ingestion. This is an internal development/test API in this increment and still requires `FLIGHT_CONTROL`, tenant context, and `Idempotency-Key`.
- Add `GET /api/v1/missions/{mission_id}/telemetry-events` to read tenant-scoped event history.
- Add `GET /api/v1/missions/{mission_id}/telemetry/ws` WebSocket. The first version sends a current snapshot and closes; live fan-out and 1-second streaming are later work.

## API And Security

- REST reads and writes use the existing bearer token, controlled `X-Tenant-Id`, and `FLIGHT_CONTROL` checks.
- WebSocket reads `Authorization` and optional `X-Tenant-Id` from headers and applies the same tenant/feature checks.
- Cross-tenant mission access returns or emits `TENANT_404` without revealing resource existence.
- Missing write idempotency returns `IDEMP_409`.

## Event Payload

`payload_json` stores the fixed `schema:flight_event_payload` outer shape:

- `event_code`
- `event_time`
- `device_sn`
- `raw_payload`

The first telemetry path supports battery, signal, location, altitude, heading, weather, and mission status fields inside `raw_payload`. Unknown fields remain in `raw_payload` for traceability but do not become production telemetry guarantees.

## Boundary

This unit uses simulator or caller-provided normalized telemetry only. It does not subscribe to real DJI topics, does not persist abnormal event linkage beyond raw `flight_events`, does not implement U1-F09 exception linkage, does not update the mission state machine from telemetry payloads, and does not provide production-grade continuous WebSocket broadcasting.
