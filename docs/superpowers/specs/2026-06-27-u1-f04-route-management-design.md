# U1-F04 Route Management Design

## Scope

U1-F04 adds tenant-scoped route and route version management for the flight-control platform. It covers route metadata, traceable route versions, version asset bindings, minimal geometry validation, idempotent writes, audit logs, and FLIGHT_CONTROL-gated reads. It does not upload routes to DJI, dispatch missions, implement OA/airspace approval, or claim production GIS/DJI readiness.

## Data Model

- `routes`: tenant-owned route master record with route code, name, optional description, and audit timestamps.
- `route_versions`: immutable route version records linked to one route in the same tenant. Each version stores `version`, `route_file_uri`, `route_format`, `checksum`, `path_geom_json`, `asset_bindings`, `validation_report`, optional `dji_route_id`, and timestamps.

No new route status enum is introduced in this unit. Version traceability is provided by append-only version records and unique `(tenant_id, route_id, version)`.

## API

Read APIs are available to tenants with `FLIGHT_CONTROL`:

- `GET /api/v1/routes`
- `GET /api/v1/routes/{route_id}`
- `GET /api/v1/routes/{route_id}/versions`
- `GET /api/v1/routes/{route_id}/versions/{version_id}`

Admin write APIs follow the existing U1-F02/U1-F03 conservative pattern: only platform administrators can write on behalf of a service tenant through controlled `X-Tenant-Id`.

- `POST /api/v1/admin/routes`
- `PATCH /api/v1/admin/routes/{route_id}`
- `POST /api/v1/admin/routes/{route_id}/versions`

All write APIs require `Idempotency-Key`, reject client supplied `tenant_id`, and write audit records.

## Validation

Route versions require:

- `route_format` in `DJI_WPML`, `KML`, `GEOJSON`, or `PENDING_CONFIRMATION`.
- `checksum` beginning with `sha256:`.
- `path_geom_json.type == "LineString"`.
- `asset_bindings` as a list of objects with `asset_type` in `road`, `bridge`, or `slope`, and an `asset_id` visible in the same tenant.

Invalid route or version input returns `MISSION_422`. Invalid geometry or asset binding returns `GIS_422`. Cross-tenant reads return `TENANT_404` and are audited without leaking existence.

## Boundaries

Real DJI route upload, route format conversion, route conflict checking, flight-safety validation, automatic GIS snapping, and customer self-service route writing remain out of scope for this unit. DJI Cloud API version, real route payload schema, customer GIS source, authoritative CRS, and stake mapping remain pending confirmation.

## Testing

Tests cover metadata and Alembic migration round trip, tenant-filtered repository reads, idempotent route creation, version creation with same-tenant asset binding, invalid geometry/checksum/asset binding, API tenant isolation, feature authorization, platform-only writes, OpenAPI exposure, and audit records.
