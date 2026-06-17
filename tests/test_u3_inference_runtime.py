import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.errors import DomainError
from drone_inspection.inference import (
    BBox,
    Detection,
    InferenceRuntime,
    PredictRequest,
    compare_backend_outputs,
)


class U3InferenceRuntimeTests(unittest.TestCase):
    def test_predict_contract_requires_valid_backend_and_input_source(self):
        with self.assertRaises(DomainError) as raised:
            PredictRequest(
                inference_job_id="job_001",
                algorithm_id="alg_road_crack",
                model_version_id="mv_001",
                frame_asset_id="frm_001",
                image_width=1920,
                image_height=1080,
                backend="cpu",
            )
        self.assertEqual(raised.exception.code, "RUNTIME_428")

        with self.assertRaises(DomainError) as raised:
            PredictRequest(
                inference_job_id="job_001",
                algorithm_id="alg_road_crack",
                model_version_id="mv_001",
                frame_asset_id="frm_001",
                image_width=1920,
                image_height=1080,
                backend="nvidia",
            )
        self.assertEqual(raised.exception.code, "INFER_504")

    def test_predict_response_preserves_backend_and_detection_geometry(self):
        runtime = InferenceRuntime()
        request = PredictRequest(
            inference_job_id="job_001",
            algorithm_id="alg_road_crack",
            model_version_id="mv_001",
            frame_asset_id="frm_001",
            image_uri="t_customer_001/proj_001/ms_001/frames/frm_001.jpg",
            image_width=1920,
            image_height=1080,
            backend="nvidia",
        )

        response = runtime.predict(
            request,
            detections=[
                Detection(
                    label="road_crack",
                    confidence=0.91,
                    bbox=BBox(x=1, y=2, width=30, height=10),
                )
            ],
        )

        self.assertEqual(response.status, "SUCCEEDED")
        self.assertEqual(response.backend, "nvidia")
        self.assertEqual(response.detections[0].geometry_type, "bbox")

        with self.assertRaises(DomainError):
            Detection(
                label="bad",
                confidence=0.5,
                bbox=BBox(x=1, y=2, width=3, height=4),
                polyline=[(1, 2), (3, 4)],
            )

    def test_backend_difference_over_threshold_blocks_release(self):
        nvidia = [Detection("road_crack", 0.91, bbox=BBox(0, 0, 10, 10))]
        domestic = [Detection("road_crack", 0.40, bbox=BBox(0, 0, 10, 10))]

        gate = compare_backend_outputs(
            frame_asset_id="frm_001",
            model_version_id="mv_001",
            nvidia=nvidia,
            domestic=domestic,
            max_confidence_delta=0.1,
        )

        self.assertFalse(gate.allowed)
        self.assertEqual(gate.error_code, "RUNTIME_428")


if __name__ == "__main__":
    unittest.main()
