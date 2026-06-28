import sys
import unittest
import warnings
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import delete

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=Warning,
    module="fastapi.testclient",
)

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.main import create_app
from app.models import (
    Base,
    DeviceModel,
    DockModel,
    MissionModel,
    RoadAssetModel,
    RouteModel,
    RouteVersionModel,
    TenantFeatureEntitlementModel,
)


class U2MediaIngestApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        database_path = (Path(self.temp_dir.name) / "api.db").as_posix()
        self.database_url = f"sqlite+pysqlite:///{database_path}"
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
        self.client = TestClient(create_app(database_url_override=self.database_url))

    def tearDown(self):
        self.client.close()
        self.client.app.state.session_factory.kw["bind"].dispose()
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    def customer_headers(self, idempotency_key: str | None = None) -> dict:
        headers = {"Authorization": "Bearer demo-customer-a"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def valid_payload(self) -> dict:
        return {
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
            headers=self.customer_headers(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_media_ingest_requires_vision_analysis_entitlement(self):
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code
                    == "VISION_ANALYSIS_RESULT",
                )
            )
            session.commit()

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


if __name__ == "__main__":
    unittest.main()
