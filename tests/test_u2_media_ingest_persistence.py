import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import inspect, select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.database import build_session_factory
from app.bootstrap import bootstrap_u0
from app.models import (
    AuditLogModel,
    Base,
    DeviceModel,
    DockModel,
    MediaChunkModel,
    MissionModel,
    RoadAssetModel,
    RouteModel,
    RouteVersionModel,
)
from app.repositories import RequestMeta
from drone_inspection.errors import DomainError


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

    def test_metadata_create_all_creates_media_chunks(self):
        session_factory = build_session_factory("sqlite+pysqlite:///:memory:")
        engine = session_factory.kw["bind"]
        try:
            Base.metadata.create_all(engine)
            self.assertIn("media_chunks", set(inspect(engine).get_table_names()))
        finally:
            engine.dispose()


class U2MediaIngestServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.database_url = f"sqlite+pysqlite:///{Path(self.temp_dir.name) / 'svc.db'}"
        self.session_factory = build_session_factory(self.database_url)
        Base.metadata.create_all(self.session_factory.kw["bind"])
        with self.session_factory() as session:
            bootstrap_u0(session)
            session.add_all(
                [
                    DeviceModel(
                        id="dev_dock_a",
                        tenant_id="t_customer_001",
                        device_type="DOCK",
                        name="Dock A",
                        manufacturer="DJI",
                        serial_number="dock-a",
                    ),
                    DeviceModel(
                        id="dev_dock_b",
                        tenant_id="t_customer_002",
                        device_type="DOCK",
                        name="Dock B",
                        manufacturer="DJI",
                        serial_number="dock-b",
                    ),
                    DockModel(
                        id="dock_a",
                        tenant_id="t_customer_001",
                        device_id="dev_dock_a",
                    ),
                    DockModel(
                        id="dock_b",
                        tenant_id="t_customer_002",
                        device_id="dev_dock_b",
                    ),
                    RoadAssetModel(
                        id="road_a",
                        tenant_id="t_customer_001",
                        route_code="G60",
                        road_name="G60 Main",
                        direction="UP",
                        start_stake=100,
                        end_stake=200,
                        geom_json={"type": "LineString", "coordinates": []},
                    ),
                    RoadAssetModel(
                        id="road_b",
                        tenant_id="t_customer_002",
                        route_code="G45",
                        road_name="G45 Main",
                        direction="DOWN",
                        start_stake=100,
                        end_stake=200,
                        geom_json={"type": "LineString", "coordinates": []},
                    ),
                    RouteModel(
                        id="route_a",
                        tenant_id="t_customer_001",
                        route_code="G60-DAILY",
                        name="G60 daily",
                    ),
                    RouteModel(
                        id="route_b",
                        tenant_id="t_customer_002",
                        route_code="G45-DAILY",
                        name="G45 daily",
                    ),
                    RouteVersionModel(
                        id="rv_a",
                        tenant_id="t_customer_001",
                        route_id="route_a",
                        version="v1",
                        route_file_uri="t_customer_001/routes/g60/v1.wpml",
                        route_format="DJI_WPML",
                        checksum="sha256:" + "a" * 64,
                        path_geom_json={"type": "LineString", "coordinates": []},
                    ),
                    RouteVersionModel(
                        id="rv_b",
                        tenant_id="t_customer_002",
                        route_id="route_b",
                        version="v1",
                        route_file_uri="t_customer_002/routes/g45/v1.wpml",
                        route_format="DJI_WPML",
                        checksum="sha256:" + "b" * 64,
                        path_geom_json={"type": "LineString", "coordinates": []},
                    ),
                ]
            )
            session.commit()
            session.add_all(
                [
                    MissionModel(
                        id="ms_a",
                        tenant_id="t_customer_001",
                        route_id="route_a",
                        route_version_id="rv_a",
                        device_id="dev_dock_a",
                        dock_id="dock_a",
                        status="DRAFT",
                        schedule_time=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
                        inspection_targets=[
                            {"asset_type": "road", "asset_id": "road_a"}
                        ],
                        media_policy={"video": True},
                    ),
                    MissionModel(
                        id="ms_other_tenant",
                        tenant_id="t_customer_002",
                        route_id="route_b",
                        route_version_id="rv_b",
                        device_id="dev_dock_b",
                        dock_id="dock_b",
                        status="DRAFT",
                        schedule_time=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
                        inspection_targets=[
                            {"asset_type": "road", "asset_id": "road_b"}
                        ],
                        media_policy={"video": True},
                    ),
                ]
            )
            session.commit()

    def tearDown(self):
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    @contextmanager
    def session_scope(self):
        with self.session_factory() as session:
            yield session

    def valid_ingest_payload(self) -> dict:
        return {
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
        }

    def test_ingest_event_creates_ready_media_and_chunks_once(self):
        from app.media_ingest import MediaIngestService

        with self.session_scope() as session:
            service = MediaIngestService(session)
            first = service.ingest_event(
                actor_id="usr_customer_admin",
                tenant_id="t_customer_001",
                values=self.valid_ingest_payload(),
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
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.action == "media_ingested",
                    AuditLogModel.resource_id == first["id"],
                )
            )

        self.assertEqual(replay["id"], first["id"])
        self.assertEqual(first["status"], "READY")
        self.assertEqual(first["chunk_summary"]["chunk_total"], 2)
        self.assertEqual(first["chunk_summary"]["chunk_completed"], 2)
        self.assertIsNotNone(audit)

    def test_ingest_rejects_cross_tenant_storage_uri_with_tenant_403(self):
        from app.media_ingest import MediaIngestService

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
        from app.media_ingest import MediaIngestService

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
        from app.media_ingest import MediaIngestService

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
        from app.media_ingest import MediaIngestService

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
        from app.media_ingest import MediaIngestService

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
        from app.media_ingest import MediaIngestService

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
            persisted_count = len(session.scalars(select(MediaChunkModel)).all())
            with self.assertRaises(DomainError) as raised:
                service.list_chunks("t_customer_002", media["id"])
        self.assertEqual(len(chunks), 2)
        self.assertEqual(persisted_count, 2)
        self.assertEqual(raised.exception.code, "TENANT_404")


if __name__ == "__main__":
    unittest.main()
