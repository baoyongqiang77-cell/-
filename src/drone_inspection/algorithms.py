from __future__ import annotations

from dataclasses import dataclass

from .constants import PHASE_ONE_ALGORITHMS


@dataclass(frozen=True)
class AlgorithmEvidence:
    real_model: bool
    metrics: dict[str, float]
    frozen_dataset_checksum: str | None
    replay_record_uri: str | None
    manual_sampling_record_uri: str | None


@dataclass(frozen=True)
class AlgorithmValidationResult:
    passed: bool
    reason: str


class AlgorithmRegistry:
    def __init__(self, algorithms: list[dict]):
        self.algorithms = list(algorithms)
        self.by_code = {algorithm["code"]: algorithm for algorithm in algorithms}

    @classmethod
    def phase_one(cls) -> "AlgorithmRegistry":
        return cls(PHASE_ONE_ALGORITHMS)

    def codes(self) -> list[str]:
        return [algorithm["code"] for algorithm in self.algorithms]

    def metrics_meet_target(self, code: str, metrics: dict[str, float]) -> bool:
        target = self.by_code[code]["target"]
        return all(metrics.get(metric, -1.0) >= minimum for metric, minimum in target.items())

    def validate_evidence(
        self,
        code: str,
        evidence: AlgorithmEvidence,
    ) -> AlgorithmValidationResult:
        if code not in self.by_code:
            return AlgorithmValidationResult(False, "算法不在一期 14 算法清单内")
        if not evidence.real_model:
            return AlgorithmValidationResult(False, "模拟算法不得计入 M2 一期最终验收")
        if not evidence.frozen_dataset_checksum:
            return AlgorithmValidationResult(False, "缺少冻结验收集 checksum")
        if not evidence.replay_record_uri:
            return AlgorithmValidationResult(False, "缺少视频回放记录")
        if not evidence.manual_sampling_record_uri:
            return AlgorithmValidationResult(False, "缺少人工抽检记录")
        if not self.metrics_meet_target(code, evidence.metrics):
            return AlgorithmValidationResult(False, "离线指标未达到算法验收目标")
        return AlgorithmValidationResult(True, "算法验收证据满足 M2 准入")

    def validate_all(
        self,
        evidence_by_code: dict[str, AlgorithmEvidence],
    ) -> AlgorithmValidationResult:
        missing = [code for code in self.codes() if code not in evidence_by_code]
        if missing:
            return AlgorithmValidationResult(False, "缺少 14 算法验收证据: " + ",".join(missing))
        for code in self.codes():
            result = self.validate_evidence(code, evidence_by_code[code])
            if not result.passed:
                return AlgorithmValidationResult(False, f"{code}: {result.reason}")
        return AlgorithmValidationResult(True, "14 算法全部通过")

