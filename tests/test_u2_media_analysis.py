import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.errors import DomainError
from drone_inspection.media_analysis import MediaAnalysisPipeline


class U2MediaAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = MediaAnalysisPipeline()

    def test_media_ingest_is_idempotent_and_checksum_checked(self):
        media = self.pipeline.ingest_media(
            tenant_id="t_customer_001",
            mission_id="ms_001",
            storage_uri="t_customer_001/proj_001/ms_001/media/med_001.mp4",
            checksum="sha256:abc",
            idempotency_key="media-callback-001",
        )
        replay = self.pipeline.ingest_media(
            tenant_id="t_customer_001",
            mission_id="ms_001",
            storage_uri="t_customer_001/proj_001/ms_001/media/med_001.mp4",
            checksum="sha256:abc",
            idempotency_key="media-callback-001",
        )

        self.assertEqual(replay.id, media.id)
        self.assertEqual(media.status, "READY")

        with self.assertRaises(DomainError) as raised:
            self.pipeline.ingest_media(
                tenant_id="t_customer_001",
                mission_id="ms_001",
                storage_uri="t_customer_001/proj_001/ms_001/media/med_001.mp4",
                checksum="sha256:different",
                idempotency_key="media-callback-002",
            )
        self.assertEqual(raised.exception.code, "MEDIA_499")

    def test_frame_analysis_event_work_order_loop_is_tenant_scoped(self):
        media = self.pipeline.ingest_media(
            tenant_id="t_customer_001",
            mission_id="ms_001",
            storage_uri="t_customer_001/proj_001/ms_001/media/med_001.mp4",
            checksum="sha256:abc",
            idempotency_key="media-callback-003",
        )
        frames = self.pipeline.extract_frames(media.id, count=2)
        task = self.pipeline.create_analysis_task(
            tenant_id="t_customer_001",
            media_file_id=media.id,
            algorithm_codes=["road_crack", "road_pothole"],
            priority="NORMAL",
        )
        event = self.pipeline.complete_analysis_with_detection(
            task_id=task.id,
            frame_asset_id=frames[0].id,
            label="road_crack",
            confidence=0.88,
        )
        work_order = self.pipeline.dispatch_work_order(event.id, actor="reviewer")

        self.assertEqual(task.status, "COMPLETED")
        self.assertEqual(event.status, "DISPATCHED")
        self.assertEqual(work_order.tenant_id, "t_customer_001")
        self.assertTrue(frames[0].storage_uri.startswith("t_customer_001/"))

        with self.assertRaises(DomainError) as raised:
            self.pipeline.get_event(event.id, tenant_id="t_customer_002")
        self.assertEqual(raised.exception.code, "TENANT_404")


if __name__ == "__main__":
    unittest.main()
