# U2-F01 Media Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persisted U2 media ingest entry point with tenant isolation, idempotency, checksum validation, chunk resume metadata, audit logs, and API tests.

**Architecture:** Keep U1 `sync-media` intact as the DJI flight-event bridge, and add a U2 `POST /api/v1/media/ingest-events` service that can register media already uploaded through the approved gateway/object-storage path. Extend `media_files` and add `media_chunks`; do not implement frame extraction or analysis task creation in this increment.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy ORM, Alembic, pytest/unittest, existing `U0Repository.run_idempotent`, existing unified `DomainError` response handling.

---

## Scope Boundary

U2-F01 includes:

- `POST /api/v1/media/ingest-events`
- `GET /api/v1/media/files/{media_file_id}`
- `GET /api/v1/media/files/{media_file_id}/chunks`
- persisted `media_chunks`
- additional `media_files` metadata required by ingest
- checksum and tenant path validation
- repeat ingest idempotency
- chunk completion summary stored as metadata
- `VISION_ANALYSIS_RESULT` entitlement on U2 read/write APIs
- audit action `media_ingested`

U2-F01 excludes:

- actual object upload streaming
- object-storage existence checks
- frame extraction
- `frame_assets`
- `analysis_tasks`
- inference queueing
- alerts and work orders

## File Structure

- Modify `apps/api/app/models.py`: extend `MediaFileModel`; add `MediaChunkModel`.
- Add `alembic/versions/20260628_0011_u2_media_ingest.py`: schema migration after `20260628_0010`.
- Add `apps/api/app/media_ingest.py`: U2 media ingest service, payload serializer, validation helpers.
- Modify `apps/api/app/main.py`: Pydantic request/response models and three U2 routes.
- Modify `tests/test_u0_persistence.py`: expected table list includes `media_chunks`.
- Modify `tests/test_u1_mission_creation_persistence.py`: preserve existing `media_files` constraints under new nullable/source-event-compatible schema.
- Add `tests/test_u2_media_ingest_persistence.py`: model and service tests.
- Add `tests/test_api_u2_media_ingest.py`: API and OpenAPI tests.
- Modify `docs/60-test-reports/U2-media-ingest-test-report.md`: create concise evidence note after tests pass.

---

### Task 1: Persistence Tests for U2 Media Schema

**Files:**
- Modify: `tests/test_u0_persistence.py`
- Add: `tests/test_u2_media_ingest_persistence.py`

- [ ] **Step 1: Add table expectation**

In `tests/test_u0_persistence.py`, add `"media_chunks"` to the expected table list next to `"media_files"`.

- [ ] **Step 2: Add failing metadata tests**

Create `tests/test_u2_media_ingest_persistence.py`:

```python
import unittest

from sqlalchemy import inspect

from app.database import Base, DatabaseSettings, create_engine_from_settings


class U2MediaIngestPersistenceTests(unittest.TestCase):
    def test_media_file_model_contains_u2_ingest_columns(self):
        table = Base.metadata.tables["media_files"]
        for column in (
            "source_type",
            "original_filename",
            "mime_type",
            "size_bytes",
            "captured_at",
            "failure_reason",
        ):
            self.assertIn(column, table.c)

    def test_media_chunks_model_registers_required_constraints(self):
        table = Base.metadata.tables["media_chunks"]
        constraints = {constraint.name for constraint in table.constraints}
        self.assertIn("fk_media_chunks_tenant_media_file", constraints)
        self.assertIn("uq_media_chunks_tenant_media_file_index", constraints)
        self.assertIn("ck_media_chunks_status", constraints)
        self.assertIn("ck_media_chunks_index_range", constraints)

    def test_alembic_upgrade_creates_media_chunks(self):
        engine = create_engine_from_settings(DatabaseSettings(url="sqlite:///:memory:"))
        Base.metadata.create_all(engine)
        self.assertIn("media_chunks", set(inspect(engine).get_table_names()))
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
pytest tests/test_u2_media_ingest_persistence.py tests/test_u0_persistence.py -q
```

Expected: fails because `media_chunks` and U2 columns do not exist.

---

### Task 2: Add ORM Models and Migration

**Files:**
- Modify: `apps/api/app/models.py`
- Add: `alembic/versions/20260628_0011_u2_media_ingest.py`

- [ ] **Step 1: Extend `MediaFileModel`**

Add nullable U2 metadata columns so existing U1 rows remain valid:

```python
source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
failure_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
```

- [ ] **Step 2: Add `MediaChunkModel`**

Add below `MediaFileModel`:

```python
class MediaChunkModel(Base):
    __tablename__ = "media_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "media_file_id"],
            ["media_files.tenant_id", "media_files.id"],
            name="fk_media_chunks_tenant_media_file",
        ),
        UniqueConstraint(
            "tenant_id",
            "media_file_id",
            "chunk_index",
            name="uq_media_chunks_tenant_media_file_index",
        ),
        CheckConstraint(
            "status IN ('UPLOADED', 'CHECKSUM_FAILED')",
            name="ck_media_chunks_status",
        ),
        CheckConstraint(
            "chunk_index >= 1 AND chunk_total >= chunk_index",
            name="ck_media_chunks_index_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    media_file_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_total: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
```

- [ ] **Step 3: Add Alembic migration**

Create `alembic/versions/20260628_0011_u2_media_ingest.py` with `down_revision = "20260628_0010"`. The upgrade must add the six U2 `media_files` columns and create `media_chunks` with the same constraints as the ORM. The downgrade must drop `media_chunks` first, then drop the six columns.

- [ ] **Step 4: Run persistence tests**

Run:

```powershell
pytest tests/test_u2_media_ingest_persistence.py tests/test_u0_persistence.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/models.py alembic/versions/20260628_0011_u2_media_ingest.py tests/test_u0_persistence.py tests/test_u2_media_ingest_persistence.py
git commit -m "feat: add U2 media ingest schema"
```

---

### Task 3: Service Tests for Media Ingest

**Files:**
- Modify: `tests/test_u2_media_ingest_persistence.py`
- Add later: `apps/api/app/media_ingest.py`

- [ ] **Step 1: Add service tests**

Append tests that seed a mission using existing test helpers/patterns from `tests/test_u1_mission_creation_persistence.py`, then call `MediaIngestService`:

```python
def test_ingest_event_creates_ready_media_and_chunks_once(self):
    from app.media_ingest import MediaIngestService
    from app.repositories import RequestMeta

    with self.session_scope() as session:
        service = MediaIngestService(session)
        first = service.ingest_event(
            actor_id="usr_customer_admin",
            tenant_id="t_customer_001",
            values={
                "mission_id": "ms_a",
                "source_type": "DJI_DOCK_3",
                "media_id": "med_u2_001",
                "media_type": "VIDEO",
                "storage_uri": "t_customer_001/proj_001/ms_a/media/med_u2_001.mp4",
                "checksum": "sha256:" + "a" * 64,
                "captured_at": "2026-06-16T10:05:30Z",
                "original_filename": "med_u2_001.mp4",
                "mime_type": "video/mp4",
                "size_bytes": 1048576,
                "chunks": [
                    {
                        "chunk_index": 1,
                        "chunk_total": 2,
                        "size_bytes": 524288,
                        "checksum": "sha256:" + "b" * 64,
                    },
                    {
                        "chunk_index": 2,
                        "chunk_total": 2,
                        "size_bytes": 524288,
                        "checksum": "sha256:" + "c" * 64,
                    },
                ],
            },
            idempotency_key="u2-ingest-001",
            request_meta=RequestMeta("req_u2_ingest_001", "127.0.0.1"),
        )
        replay = service.ingest_event(
            actor_id="usr_customer_admin",
            tenant_id="t_customer_001",
            values=first["payload_json"]["ingest_request"],
            idempotency_key="u2-ingest-001",
            request_meta=RequestMeta("req_u2_ingest_001", "127.0.0.1"),
        )

    self.assertEqual(replay["id"], first["id"])
    self.assertEqual(first["status"], "READY")
    self.assertEqual(first["chunk_summary"]["chunk_total"], 2)
    self.assertEqual(first["chunk_summary"]["chunk_completed"], 2)
```

Add separate tests with the same base payload:

```python
def test_ingest_rejects_cross_tenant_storage_uri_with_tenant_403(self):
    payload = self.valid_ingest_payload()
    payload["storage_uri"] = "t_customer_002/proj_001/ms_a/media/med_u2_001.mp4"
    with self.session_scope() as session:
        service = MediaIngestService(session)
        with self.assertRaises(DomainError) as raised:
            service.ingest_event(
                "usr_customer_admin",
                "t_customer_001",
                payload,
                "u2-cross-path",
                RequestMeta("req_u2_cross_path", "127.0.0.1"),
            )
    self.assertEqual(raised.exception.code, "TENANT_403")

def test_ingest_rejects_unsupported_mime_with_media_415(self):
    payload = self.valid_ingest_payload()
    payload["mime_type"] = "application/octet-stream"
    with self.session_scope() as session:
        service = MediaIngestService(session)
        with self.assertRaises(DomainError) as raised:
            service.ingest_event(
                "usr_customer_admin",
                "t_customer_001",
                payload,
                "u2-bad-mime",
                RequestMeta("req_u2_bad_mime", "127.0.0.1"),
            )
    self.assertEqual(raised.exception.code, "MEDIA_415")

def test_ingest_rejects_bad_checksum_with_media_499(self):
    payload = self.valid_ingest_payload()
    payload["checksum"] = "sha256:not-valid"
    with self.session_scope() as session:
        service = MediaIngestService(session)
        with self.assertRaises(DomainError) as raised:
            service.ingest_event(
                "usr_customer_admin",
                "t_customer_001",
                payload,
                "u2-bad-checksum",
                RequestMeta("req_u2_bad_checksum", "127.0.0.1"),
            )
    self.assertEqual(raised.exception.code, "MEDIA_499")

def test_ingest_rejects_incomplete_chunks_with_media_499(self):
    payload = self.valid_ingest_payload()
    payload["chunks"] = [
        {
            "chunk_index": 2,
            "chunk_total": 2,
            "size_bytes": 524288,
            "checksum": "sha256:" + "b" * 64,
        }
    ]
    with self.session_scope() as session:
        service = MediaIngestService(session)
        with self.assertRaises(DomainError) as raised:
            service.ingest_event(
                "usr_customer_admin",
                "t_customer_001",
                payload,
                "u2-incomplete-chunks",
                RequestMeta("req_u2_incomplete_chunks", "127.0.0.1"),
            )
    self.assertEqual(raised.exception.code, "MEDIA_499")

def test_ingest_cross_tenant_mission_returns_tenant_404(self):
    payload = self.valid_ingest_payload()
    payload["mission_id"] = "ms_other_tenant"
    with self.session_scope() as session:
        service = MediaIngestService(session)
        with self.assertRaises(DomainError) as raised:
            service.ingest_event(
                "usr_customer_admin",
                "t_customer_001",
                payload,
                "u2-cross-mission",
                RequestMeta("req_u2_cross_mission", "127.0.0.1"),
            )
    self.assertEqual(raised.exception.code, "TENANT_404")

def test_list_chunks_is_tenant_scoped(self):
    with self.session_scope() as session:
        service = MediaIngestService(session)
        media = service.ingest_event(
            "usr_customer_admin",
            "t_customer_001",
            self.valid_ingest_payload(),
            "u2-list-chunks",
            RequestMeta("req_u2_list_chunks", "127.0.0.1"),
        )
        chunks = service.list_chunks("t_customer_001", media["id"])
        with self.assertRaises(DomainError) as raised:
            service.list_chunks("t_customer_002", media["id"])
    self.assertEqual(len(chunks), 2)
    self.assertEqual(raised.exception.code, "TENANT_404")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
pytest tests/test_u2_media_ingest_persistence.py -q
```

Expected: fails because `app.media_ingest.MediaIngestService` does not exist.

---

### Task 4: Implement Media Ingest Service

**Files:**
- Add: `apps/api/app/media_ingest.py`

- [ ] **Step 1: Create service module**

Implement:

```python
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from json import dumps
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import MediaChunkModel, MediaFileModel, MissionModel
from .repositories import RequestMeta, U0Repository


SUPPORTED_SOURCE_TYPES = {"DJI_DOCK_3", "MANUAL_IMPORT", "SIMULATOR"}
SUPPORTED_MEDIA_TYPES = {"VIDEO", "IMAGE", "THUMBNAIL"}
SUPPORTED_MIME_TYPES = {"video/mp4", "image/jpeg", "image/png"}
CHECKSUM_PATTERN = re.compile(r"^(sha256:[0-9a-fA-F]{64}|md5:[0-9a-fA-F]{32})$")


def media_ingest_payload(item: MediaFileModel, chunk_completed: int = 0, chunk_total: int = 0) -> dict:
    payload = {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "device_id": item.device_id,
        "source_event_id": item.source_event_id,
        "media_id": item.media_id,
        "media_type": item.media_type,
        "source_type": item.source_type,
        "storage_uri": item.storage_uri,
        "checksum": item.checksum,
        "original_filename": item.original_filename,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "captured_at": item.captured_at.isoformat() if item.captured_at else None,
        "status": item.status,
        "failure_reason": item.failure_reason,
        "payload_json": item.payload_json,
        "chunk_summary": {
            "chunk_total": chunk_total,
            "chunk_completed": chunk_completed,
        },
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
    return payload
```

- [ ] **Step 2: Implement validation helpers**

Validation rules:

- `mission_id`, `media_id`, `media_type`, `source_type`, `storage_uri`, `checksum`, `captured_at`, `mime_type`, and `size_bytes` are required.
- `storage_uri` must start with `<tenant_id>/`; otherwise raise `TENANT_403`.
- `checksum` and every chunk checksum must match `CHECKSUM_PATTERN`; otherwise raise `MEDIA_499`.
- `mime_type` must be in `SUPPORTED_MIME_TYPES`; otherwise raise `MEDIA_415`.
- `media_type` must be in `SUPPORTED_MEDIA_TYPES`; otherwise raise `MEDIA_415`.
- `source_type` must be in `SUPPORTED_SOURCE_TYPES`; otherwise raise `MISSION_422`.
- chunks are optional, but if present their `chunk_index` values must cover `1..chunk_total`; otherwise raise `MEDIA_499`.

- [ ] **Step 3: Implement service methods**

Implement:

```python
class MediaIngestService:
    def __init__(self, session: Session):
        self.session = session
        self.u0 = U0Repository(session)

    def ingest_event(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        normalized = self._normalize_values(tenant_id, values)
        fingerprint = self._fingerprint(
            {
                "action": "media_ingest",
                "tenant_id": tenant_id,
                "payload": normalized,
            }
        )
        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            "media-ingest-events",
            idempotency_key,
            fingerprint,
            lambda: self._create_media(actor_id, tenant_id, normalized, request_meta),
        )

    def get_media_file(self, tenant_id: str, media_file_id: str) -> dict:
        item = self._media_file(tenant_id, media_file_id)
        chunk_total, chunk_completed = self._chunk_summary(tenant_id, media_file_id)
        return media_ingest_payload(item, chunk_completed, chunk_total)

    def list_chunks(self, tenant_id: str, media_file_id: str) -> list[dict]:
        self._media_file(tenant_id, media_file_id)
        statement = (
            select(MediaChunkModel)
            .where(
                MediaChunkModel.tenant_id == tenant_id,
                MediaChunkModel.media_file_id == media_file_id,
            )
            .order_by(MediaChunkModel.chunk_index)
        )
        return [
            {
                "id": chunk.id,
                "tenant_id": chunk.tenant_id,
                "media_file_id": chunk.media_file_id,
                "chunk_index": chunk.chunk_index,
                "chunk_total": chunk.chunk_total,
                "size_bytes": chunk.size_bytes,
                "checksum": chunk.checksum,
                "status": chunk.status,
                "created_at": chunk.created_at.isoformat(),
                "updated_at": chunk.updated_at.isoformat(),
            }
            for chunk in self.session.scalars(statement)
        ]
```

`ingest_event` must call `self.u0.run_idempotent(tenant_id, "POST", "media-ingest-events", idempotency_key, fingerprint, operation)`.

Inside `operation`:

- verify mission exists in same tenant; missing returns `TENANT_404`
- reject duplicate `(tenant_id, storage_uri)` with different checksum as `MEDIA_499`
- create `MediaFileModel(status="READY")`
- create `MediaChunkModel(status="UPLOADED")` rows for each chunk
- write audit action `media_ingested`, resource type `media_file`
- include original normalized request under `payload_json["ingest_request"]`

- [ ] **Step 4: Run service tests**

Run:

```powershell
pytest tests/test_u2_media_ingest_persistence.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/media_ingest.py tests/test_u2_media_ingest_persistence.py
git commit -m "feat: implement U2 media ingest service"
```

---

### Task 5: API Tests for U2 Media Ingest

**Files:**
- Add: `tests/test_api_u2_media_ingest.py`
- Modify later: `apps/api/app/main.py`

- [ ] **Step 1: Add API test file**

Create API tests using the same client/auth/header patterns as `tests/test_api_u1_mission_creation.py`.

Required tests:

```python
def test_customer_ingests_media_event_once_and_reads_chunks(self):
    first = self.client.post(
        "/api/v1/media/ingest-events",
        json=self.valid_payload(),
        headers=self.customer_headers("u2-api-ingest-001"),
    )
    replay = self.client.post(
        "/api/v1/media/ingest-events",
        json=self.valid_payload(),
        headers=self.customer_headers("u2-api-ingest-001"),
    )
    chunks = self.client.get(
        f"/api/v1/media/files/{first.json()['id']}/chunks",
        headers=self.customer_headers(),
    )
    self.assertEqual(first.status_code, 200)
    self.assertEqual(replay.json()["id"], first.json()["id"])
    self.assertEqual(chunks.status_code, 200)
    self.assertEqual(len(chunks.json()["items"]), 1)

def test_media_ingest_requires_idempotency_key(self):
    response = self.client.post(
        "/api/v1/media/ingest-events",
        json=self.valid_payload(),
        headers=self.customer_headers_without_idempotency(),
    )
    self.assertEqual(response.status_code, 409)
    self.assertEqual(response.json()["code"], "IDEMP_409")

def test_media_ingest_requires_vision_analysis_entitlement(self):
    self.disable_customer_feature("VISION_ANALYSIS_RESULT")
    response = self.client.post(
        "/api/v1/media/ingest-events",
        json=self.valid_payload(),
        headers=self.customer_headers("u2-api-feature-denied"),
    )
    self.assertEqual(response.status_code, 403)
    self.assertEqual(response.json()["code"], "FEATURE_403")

def test_media_ingest_bad_checksum_returns_media_499(self):
    payload = self.valid_payload()
    payload["checksum"] = "sha256:not-valid"
    response = self.client.post(
        "/api/v1/media/ingest-events",
        json=payload,
        headers=self.customer_headers("u2-api-bad-checksum"),
    )
    self.assertEqual(response.status_code, 499)
    self.assertEqual(response.json()["code"], "MEDIA_499")

def test_media_ingest_unsupported_mime_returns_media_415(self):
    payload = self.valid_payload()
    payload["mime_type"] = "application/octet-stream"
    response = self.client.post(
        "/api/v1/media/ingest-events",
        json=payload,
        headers=self.customer_headers("u2-api-bad-mime"),
    )
    self.assertEqual(response.status_code, 415)
    self.assertEqual(response.json()["code"], "MEDIA_415")

def test_media_ingest_cross_tenant_mission_returns_tenant_404(self):
    payload = self.valid_payload()
    payload["mission_id"] = "ms_other_tenant"
    response = self.client.post(
        "/api/v1/media/ingest-events",
        json=payload,
        headers=self.customer_headers("u2-api-cross-mission"),
    )
    self.assertEqual(response.status_code, 404)
    self.assertEqual(response.json()["code"], "TENANT_404")

def test_openapi_exposes_u2_media_paths(self):
    paths = self.client.get("/openapi.json").json()["paths"]
    self.assertIn("/api/v1/media/ingest-events", paths)
    self.assertIn("/api/v1/media/files/{media_file_id}", paths)
    self.assertIn("/api/v1/media/files/{media_file_id}/chunks", paths)
```

Use payload:

```python
{
    "mission_id": "ms_a",
    "source_type": "DJI_DOCK_3",
    "media_id": "med_u2_api_001",
    "media_type": "VIDEO",
    "storage_uri": "t_customer_001/proj_001/ms_a/media/med_u2_api_001.mp4",
    "checksum": "sha256:" + "a" * 64,
    "captured_at": "2026-06-16T10:05:30Z",
    "original_filename": "med_u2_api_001.mp4",
    "mime_type": "video/mp4",
    "size_bytes": 1048576,
    "chunks": [
        {
            "chunk_index": 1,
            "chunk_total": 1,
            "size_bytes": 1048576,
            "checksum": "sha256:" + "b" * 64,
        }
    ],
}
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```powershell
pytest tests/test_api_u2_media_ingest.py -q
```

Expected: fails with missing `/api/v1/media/ingest-events`.

---

### Task 6: Add FastAPI Routes

**Files:**
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Import service**

Add:

```python
from .media_ingest import MediaIngestService
```

- [ ] **Step 2: Add Pydantic request models**

Add near existing request models:

```python
class MediaChunkIngestRequest(BaseModel):
    chunk_index: int
    chunk_total: int
    size_bytes: int
    checksum: str


class MediaIngestEventRequest(BaseModel):
    mission_id: str
    source_type: str
    media_id: str
    media_type: str
    storage_uri: str
    checksum: str
    captured_at: str
    original_filename: str | None = None
    mime_type: str
    size_bytes: int
    chunks: list[MediaChunkIngestRequest] = Field(default_factory=list)
```

- [ ] **Step 3: Add routes**

Add routes after the U1 media routes:

```python
@app.post("/api/v1/media/ingest-events", tags=["U2 media"])
def ingest_media_event(
    payload: MediaIngestEventRequest,
    request: Request,
    actor: Actor = Depends(actor_from_authorization),
    repo: U0Repository = Depends(repository),
    meta: RequestMeta = Depends(request_meta),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    context = _resolve_context(request, repo, actor, x_tenant_id, meta)
    _require_feature(request, repo, actor, context, FeatureCode.VISION_ANALYSIS_RESULT, meta)
    service = MediaIngestService(repo.session)
    return service.ingest_event(
        actor.id,
        context.tenant_id,
        payload.model_dump(),
        idempotency_key,
        meta,
    )


@app.get("/api/v1/media/files/{media_file_id}", tags=["U2 media"])
def get_media_file(
    media_file_id: str,
    request: Request,
    actor: Actor = Depends(actor_from_authorization),
    repo: U0Repository = Depends(repository),
    meta: RequestMeta = Depends(request_meta),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict:
    context = _resolve_context(request, repo, actor, x_tenant_id, meta)
    _require_feature(request, repo, actor, context, FeatureCode.VISION_ANALYSIS_RESULT, meta)
    service = MediaIngestService(repo.session)
    return service.get_media_file(context.tenant_id, media_file_id)


@app.get("/api/v1/media/files/{media_file_id}/chunks", tags=["U2 media"])
def list_media_chunks(
    media_file_id: str,
    request: Request,
    actor: Actor = Depends(actor_from_authorization),
    repo: U0Repository = Depends(repository),
    meta: RequestMeta = Depends(request_meta),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict:
    context = _resolve_context(request, repo, actor, x_tenant_id, meta)
    _require_feature(request, repo, actor, context, FeatureCode.VISION_ANALYSIS_RESULT, meta)
    service = MediaIngestService(repo.session)
    return {"items": service.list_chunks(context.tenant_id, media_file_id)}
```

Use the existing dependency parameters from nearby route functions exactly: `Request`, `Actor`, `U0Repository`, `RequestMeta`, `X-Tenant-Id`, and `Idempotency-Key` for the write route.

- [ ] **Step 4: Run API tests**

Run:

```powershell
pytest tests/test_api_u2_media_ingest.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/main.py tests/test_api_u2_media_ingest.py
git commit -m "feat: expose U2 media ingest API"
```

---

### Task 7: Regression and Documentation Evidence

**Files:**
- Add: `docs/60-test-reports/U2-media-ingest-test-report.md`

- [ ] **Step 1: Run focused regression**

Run:

```powershell
pytest tests/test_u2_media_ingest_persistence.py tests/test_api_u2_media_ingest.py tests/test_api_u1_mission_creation.py tests/test_u1_mission_creation_persistence.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader existing U2 smoke**

Run:

```powershell
pytest tests/test_u2_media_analysis.py -q
```

Expected: PASS. This is legacy in-memory smoke only; do not treat it as persisted U2 acceptance.

- [ ] **Step 3: Add test report**

Create `docs/60-test-reports/U2-media-ingest-test-report.md`:

```markdown
# U2-F01 Media Ingest Test Report

Date: 2026-06-28

Scope:
- POST /api/v1/media/ingest-events
- GET /api/v1/media/files/{media_file_id}
- GET /api/v1/media/files/{media_file_id}/chunks
- media_files U2 ingest metadata
- media_chunks persistence

Verification:
- pytest tests/test_u2_media_ingest_persistence.py tests/test_api_u2_media_ingest.py tests/test_api_u1_mission_creation.py tests/test_u1_mission_creation_persistence.py -q
- pytest tests/test_u2_media_analysis.py -q

Boundary:
- This verifies media ingest registration, checksum validation, idempotency, chunk metadata, tenant isolation, feature entitlement, and audit.
- It does not verify object-storage streaming, frame extraction, analysis task creation, inference, alerts, or work orders.
```

- [ ] **Step 4: Commit**

```powershell
git add docs/60-test-reports/U2-media-ingest-test-report.md
git commit -m "docs: add U2 media ingest test report"
```

---

## Self-Review

- Spec coverage: The plan covers media ingest, chunk metadata, checksum validation, weak-network resume metadata, tenant isolation, feature entitlement, idempotency, audit, OpenAPI exposure, and test evidence.
- Scope check: Frame extraction, analysis, inference, alerts, and work orders are intentionally excluded for U2-F02+.
- Placeholder scan: No implementation step depends on an unspecified external API or real object-storage capability.
- Type consistency: `MediaIngestService.ingest_event`, `get_media_file`, and `list_chunks` are introduced before API route usage; route payload fields match service test payload fields.
