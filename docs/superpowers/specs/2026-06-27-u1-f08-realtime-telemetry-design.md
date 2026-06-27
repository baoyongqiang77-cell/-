# U1-F08 Realtime Telemetry Design

This increment upgrades the existing U1-F08 telemetry WebSocket from a snapshot-only endpoint to a simulator-backed realtime fan-out path. It keeps the current REST ingestion endpoint as the single write boundary: when a normalized simulator telemetry event is accepted, persisted, and committed, connected WebSocket clients for the same tenant and mission receive the new event.

## Scope

- Keep `POST /api/v1/missions/{mission_id}/telemetry-events` as the simulator/normalized telemetry ingestion API.
- Keep `GET /api/v1/missions/{mission_id}/telemetry-events` as the tenant-scoped event history API.
- Upgrade `GET /api/v1/missions/{mission_id}/telemetry/ws` so it:
  - authenticates with the same bearer token and optional controlled `X-Tenant-Id`;
  - validates `FLIGHT_CONTROL` and mission tenant access before subscription;
  - sends an initial snapshot after connection;
  - stays open and sends each newly persisted event for that tenant and mission;
  - removes disconnected clients without affecting later broadcasts.
- Add an in-process telemetry hub for development and tests. It is not a distributed production message bus.

## Data Flow

1. A client opens `/api/v1/missions/{mission_id}/telemetry/ws`.
2. The API authenticates the caller, resolves tenant context, checks `FLIGHT_CONTROL`, and verifies the mission belongs to the service tenant.
3. The WebSocket receives a message of type `snapshot` containing the current ordered event list.
4. A simulator or test caller posts a normalized `FlightEvent` to `/api/v1/missions/{mission_id}/telemetry-events` with `Idempotency-Key`.
5. The telemetry service persists the event exactly as U1-F08 already requires.
6. After the write succeeds, the API broadcasts a message of type `event` to subscribers keyed by `(tenant_id, mission_id)`.

## Message Shape

The WebSocket sends JSON objects with explicit message types:

```json
{
  "type": "snapshot",
  "mission_id": "ms_a",
  "items": []
}
```

```json
{
  "type": "event",
  "mission_id": "ms_a",
  "item": {
    "id": "fe_abc123",
    "tenant_id": "t_customer_001",
    "mission_id": "ms_a",
    "device_id": "dock_dev_a",
    "event_code": "telemetry",
    "event_time": "2026-07-01T09:01:00+00:00",
    "device_sn": "dock-a",
    "payload_json": {
      "event_code": "telemetry",
      "event_time": "2026-07-01T09:01:00Z",
      "device_sn": "dock-a",
      "raw_payload": {
        "battery": 82,
        "signal": -58
      }
    },
    "created_at": "2026-07-01T09:01:00+00:00"
  }
}
```

Error messages keep the existing unified error shape:

```json
{
  "code": "TENANT_404",
  "message": "Mission does not exist or is not accessible",
  "request_id": "req_8f3a1c2d",
  "details": {}
}
```

## Security And Tenant Rules

- WebSocket subscriptions are keyed by the resolved service tenant and mission, never by client-provided tenant values alone.
- Customer tenants cannot use `X-Tenant-Id` to switch tenants.
- Cross-tenant mission subscriptions return a `TENANT_404` error message and close.
- Tenants without `FLIGHT_CONTROL` receive `FEATURE_403` and close.
- Broadcasts never scan or send to subscribers for other tenants.

## Boundaries

This is a simulator realtime loop for M1 development evidence. It does not connect to real DJI Cloud API, does not subscribe to DJI MQTT or WebSocket topics, does not implement a distributed production pub/sub layer, does not guarantee production 1-second telemetry, and does not update mission state from telemetry payloads. Real DJI telemetry adapters and production fan-out infrastructure remain separate later work after DJI credentials, callback/topic protocol, and deployment topology are confirmed.

## Tests

- WebSocket subscribers receive an initial `snapshot` and stay connected.
- After telemetry POST succeeds, the subscriber receives a typed `event` message without reconnecting.
- A second tenant cannot subscribe to another tenant's mission.
- A tenant without `FLIGHT_CONTROL` receives `FEATURE_403` and no subscription is registered.
- Disconnecting a WebSocket removes it from the in-process hub and does not break future broadcasts.
