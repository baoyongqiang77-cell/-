# U1-F10 Media Sync Design

## Purpose

U1-F10 adds the flight-control media sync boundary for DJI Dock 3 simulator callbacks. It converts a normalized `media_upload_completed` flight event into a tenant-scoped platform media record that can be listed from the mission context.

This increment is deliberately limited to U1. It does not extract frames, enqueue U2 analysis, call an object storage API, generate visual-analysis alerts, or create work orders.

## Scope

In scope:

- Persist media files linked to a mission, device, tenant, and source `flight_events` row.
- Accept only normalized `media_upload_completed` events from the existing U1 telemetry event table.
- Validate same-tenant and same-mission relationships.
- Validate the media payload contains a media id, storage URI, checksum, and media type.
- Preserve source callback payload for auditability.
- Expose write and read REST APIs under the mission boundary.
- Enforce `FLIGHT_CONTROL`, tenant isolation, idempotency, fixed error responses, and audit logs.

Out of scope:

- U2 media ingest, chunk upload, breakpoint resume, or frame extraction.
- `analysis_tasks`, `inference_jobs`, alerts, review records, and work orders.
- Real DJI Cloud API subscription or production media callback signature validation.
- Real object storage connectivity or object existence checks.
- Mission status transition to `MEDIA_SYNCING`, `PARTIAL_MEDIA_READY`, or `MEDIA_READY`.

## Data Model

Add `media_files` as the first durable media table used by U1-F10 and later U2 work. The table keeps the tenant boundary explicit and links back to the source flight event.

Required columns:

- `id`
- `tenant_id`
- `mission_id`
- `device_id`
- `source_event_id`
- `media_id`
- `media_type`
- `storage_uri`
- `checksum`
- `status`
- `payload_json`
- `created_at`
- `updated_at`

Constraints:

- `tenant_id` references `tenants.id`.
- `(tenant_id, mission_id)` references `(missions.tenant_id, missions.id)`.
- `source_event_id` references `flight_events.id`.
- `(tenant_id, source_event_id)` is unique, so one source event creates at most one media record.
- `status` uses the existing media status enum set: `CAPTURED`, `UPLOADING`, `UPLOAD_FAILED`, `REGISTERING`, `READY`, `REJECTED`, `FRAME_EXTRACTING`, `FRAME_READY`, `ARCHIVED`, `DELETED`.
- U1-F10 successful sync stores `READY`.

The table intentionally does not create `media_chunks` or `frame_assets`. Those are U2 concerns.

## Event Mapping

Only `flight_events.event_code == "media_upload_completed"` is accepted.

The source payload must include:

- `event_code`
- `event_time`
- `device_sn`
- `raw_payload.media_id`
- `raw_payload.storage_uri`
- `raw_payload.checksum`
- `raw_payload.media_type`

The first implementation accepts `media_type` values `VIDEO`, `IMAGE`, and `THUMBNAIL`. Unsupported event codes return `MISSION_422`. Missing or malformed checksum values return `MEDIA_499`.

The storage URI must be tenant-scoped by prefix: it must start with `<tenant_id>/`. This keeps the object path isolation rule visible even though U1-F10 does not call the object storage backend.

## APIs

Add:

- `POST /api/v1/missions/{mission_id}/flight-events/{flight_event_id}/sync-media`
- `GET /api/v1/missions/{mission_id}/media-files`

The write API:

- Requires bearer authentication.
- Requires `FLIGHT_CONTROL`.
- Requires `Idempotency-Key`.
- Uses controlled `X-Tenant-Id` only through the existing tenant context rules.
- Returns the media file payload.
- Writes a `media_file_synced` audit log.

The read API:

- Requires bearer authentication.
- Requires `FLIGHT_CONTROL`.
- Lists only media records for the current service tenant and mission.
- Returns `TENANT_404` for cross-tenant mission access.

## Error Handling

Use the existing unified error response shape.

Expected errors:

- `FEATURE_403`: current tenant lacks `FLIGHT_CONTROL`.
- `TENANT_404`: mission or source event is outside the current tenant boundary.
- `MISSION_422`: source event is not `media_upload_completed`, belongs to another mission, or lacks required media fields other than checksum.
- `MEDIA_499`: checksum is missing or does not use an accepted format.
- `IDEMP_409`: the same idempotency key is reused with a different request fingerprint, or the source event was already synced outside the replay path.

## Testing

Use TDD.

Persistence tests:

- `media_files` metadata and constraints exist.
- Alembic upgrade/downgrade/upgrade includes `media_files`.
- U0 expected table list includes `media_files`.

Service tests:

- A `media_upload_completed` flight event syncs exactly one `READY` media file and can be listed.
- Replaying the same idempotency key returns the same media file.
- A non-media event returns `MISSION_422`.
- A bad checksum returns `MEDIA_499`.
- A cross-tenant mission or event returns `TENANT_404`.
- Successful sync writes `media_file_synced` audit logs.

API tests:

- Customer tenant with `FLIGHT_CONTROL` can sync and list mission media.
- Missing `Idempotency-Key` is rejected before mutation.
- Unsupported event returns `MISSION_422`.
- Bad checksum returns `MEDIA_499`.
- Cross-tenant access does not reveal resource existence.
- Missing `FLIGHT_CONTROL` returns `FEATURE_403`.
- OpenAPI exposes both paths.

## Acceptance Boundary

U1-F10 is complete when the simulator media-upload callback can be represented as a persisted, tenant-scoped media record through the U1 mission API, with idempotency, audit, and tests. Completion does not claim real DJI production media callback integration, object storage verification, breakpoint resume, frame extraction, or U2 analysis readiness.
