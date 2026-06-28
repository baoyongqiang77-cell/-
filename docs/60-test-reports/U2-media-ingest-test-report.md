# U2-F01 Media Ingest Test Report

Date: 2026-06-28

Scope:

- `POST /api/v1/media/ingest-events`
- `GET /api/v1/media/files/{media_file_id}`
- `GET /api/v1/media/files/{media_file_id}/chunks`
- `media_files` U2 ingest metadata
- `media_chunks` persistence

Verification:

- `.\\.venv\\Scripts\\python.exe -m unittest tests.test_u2_media_ingest_persistence tests.test_api_u2_media_ingest tests.test_api_u1_mission_creation tests.test_u1_mission_creation_persistence`
- `.\\.venv\\Scripts\\python.exe -m unittest tests.test_u2_media_analysis`

Result:

- Focused U2/U1 regression: 82 tests passed.
- Legacy U2 in-memory smoke: 2 tests passed.

Boundary:

- This verifies media ingest registration, checksum validation, idempotency, chunk metadata, tenant isolation, feature entitlement, audit, and U1 media-sync compatibility.
- It does not verify object-storage streaming, frame extraction, analysis task creation, inference, alerts, or work orders.
