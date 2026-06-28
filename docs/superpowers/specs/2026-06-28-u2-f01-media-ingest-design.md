# U2-F01 Media Ingest Design

## Purpose

U2-F01 introduces the media ingest boundary for the visual analysis platform. It registers mission media as analysis-ready media records, validates tenant-scoped object paths, supported formats, and complete-file checksums, and keeps the operation idempotent.

This increment starts U2 from the clean handoff point created by U1-F10. It does not implement chunk upload, breakpoint resume, frame extraction, inference, alerts, work orders, or object storage connectivity.

## Scope

In scope:

- Add a mission-independent U2 media ingest API: `POST /api/v1/media/ingest-events`.
- Register a media ingest event against an existing `media_files` record or create a U2-ready media file record from an external ingest callback.
- Enforce current tenant context and reject cross-tenant paths.
- Validate storage URI tenant prefix.
- Validate media format by URI extension and declared media type.
- Validate full-file checksum in `sha256:<64 hex>` format.
- Return the existing record for duplicate ingest of the same URI and checksum.
- Reject duplicate ingest of the same URI with a different checksum.
- Write `media_ingested` audit logs.
- Expose the path in OpenAPI.

Out of scope:

- `media_chunks` persistence and chunk-level checksum.
- Weak-network breakpoint resume implementation.
- `frame_assets` creation and frame extraction jobs.
- `analysis_tasks`, `inference_jobs`, events, review records, and work orders.
- Real object storage reads, signed URLs, file existence checks, or MinIO/S3 connectivity.
- Mission status transitions.

## Data Model

U2-F01 reuses and minimally extends the existing `media_files` table introduced in U1-F10. U1 media sync always has a source flight event, while U2 ingest must also accept later object-storage ingest callbacks that may not have a `flight_events` row.

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

Required U2-F01 migration changes:

- Make `source_event_id` nullable so non-U1 ingest callbacks can create media records.
- Add a unique constraint on `(tenant_id, storage_uri)` so duplicate callback handling is database-backed.

U2-F01 does not add `media_chunks` or `frame_assets`. Later increments may extend the media model with size, MIME type, and retention fields if needed.

## API

Add:

- `POST /api/v1/media/ingest-events`

Request body:

```json
{
  "mission_id": "ms_a",
  "media_id": "med_001",
  "media_type": "VIDEO",
  "storage_uri": "t_customer_001/proj_001/ms_a/media/med_001.mp4",
  "checksum": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "source": "U1_MEDIA_SYNC"
}
```

Rules:

- Requires bearer authentication.
- Requires `VISION_ANALYSIS_RESULT` for read/analysis visibility or `FLIGHT_CONTROL` when ingesting from U1 mission flow. For this first ingest boundary, require `VISION_ANALYSIS_RESULT` so customer tenants can use the analysis platform surface without requiring platform-only permissions.
- Requires `Idempotency-Key`.
- Uses existing tenant context resolution. Customer tenants cannot override `tenant_id` in the request body.
- Optional controlled `X-Tenant-Id` follows existing platform operator rules.
- Successful response returns the media file payload.

## Validation

Tenant and mission:

- `mission_id` must exist in the current service tenant, otherwise return `TENANT_404`.
- `storage_uri` must start with `<tenant_id>/`, otherwise return `TENANT_403`.

Media format:

- Accepted extensions: `.mp4`, `.jpg`, `.jpeg`, `.png`.
- Accepted `media_type`: `VIDEO`, `IMAGE`, `THUMBNAIL`.
- Unsupported format or type returns `MEDIA_415`.

Checksum:

- `checksum` must match `sha256:<64 hex>`.
- Malformed checksum returns `MEDIA_499`.
- Same `storage_uri` and same `checksum` returns the existing record through idempotent replay or duplicate detection.
- Same `storage_uri` with a different checksum returns `MEDIA_499`.

Status:

- Successful ingest stores or preserves `READY`.
- Rejected records are not created in this increment; errors are returned to callers and audited by existing denial patterns where applicable.

## Service Design

Add `apps/api/app/media_ingest.py` with:

- `MediaIngestService.ingest_media`
- `MediaIngestService._mission`
- `MediaIngestService._validate_payload`
- `media_ingest_payload` or direct reuse of `media_file_payload` when importing from `media_sync.py` does not create a circular dependency.

The service should:

1. Resolve and validate tenant context.
2. Validate mission ownership.
3. Validate media type, extension, URI prefix, and checksum.
4. Check for an existing `media_files` row by `tenant_id + storage_uri`.
5. If existing checksum matches, return the existing row.
6. If existing checksum differs, raise `MEDIA_499`.
7. If absent, create `MediaFileModel` with `status = READY`, nullable `source_event_id`, and payload metadata containing `source = U2_MEDIA_INGEST`.
8. Run through U0 idempotency with a fingerprint over tenant, mission, media id, type, storage URI, checksum, and source.
9. Write `media_ingested` audit logs.

## Error Handling

Use the existing unified error response shape.

Expected errors:

- `AUTH_401`: missing or invalid bearer token.
- `FEATURE_403`: tenant lacks the required ingest feature entitlement.
- `TENANT_403`: object path is not scoped to the current tenant.
- `TENANT_404`: mission is outside the current tenant boundary.
- `MEDIA_415`: unsupported media format or media type.
- `MEDIA_499`: malformed checksum or checksum conflict.
- `IDEMP_409`: missing idempotency key or same key reused with a different fingerprint.

## Testing

Use TDD.

Persistence/model tests:

- `media_files.source_event_id` is nullable.
- `media_files` has a unique constraint for `tenant_id + storage_uri`.
- Alembic upgrade/downgrade preserves `media_files` and toggles the U2-F01 nullable/unique changes.

Service tests:

- Ingest creates a `READY` media record.
- Same idempotency key replays the same result.
- Same URI and checksum with a different key returns the existing record.
- Same URI with different checksum returns `MEDIA_499`.
- Unsupported extension returns `MEDIA_415`.
- Storage URI without tenant prefix returns `TENANT_403`.
- Cross-tenant mission returns `TENANT_404`.
- Successful ingest writes `media_ingested` audit logs.

API tests:

- Customer can ingest media with `VISION_ANALYSIS_RESULT`.
- Missing `Idempotency-Key` returns `IDEMP_409`.
- Unsupported media format returns `MEDIA_415`.
- Bad checksum returns `MEDIA_499`.
- Cross-tenant mission returns `TENANT_404`.
- Tenant path violation returns `TENANT_403`.
- Missing feature entitlement returns `FEATURE_403`.
- OpenAPI exposes `/api/v1/media/ingest-events`.

## Acceptance Boundary

U2-F01 is complete when media can be registered through the U2 ingest API as tenant-scoped, checksum-validated, idempotent, audit-backed `READY` media records. It does not prove chunk upload, weak-network resume, object storage connectivity, frame extraction, inference, alerts, or work-order readiness.
