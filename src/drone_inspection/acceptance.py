from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil


@dataclass
class AcceptanceInputs:
    unit_results: dict[str, bool]
    locked_external_interfaces: bool
    locked_domestic_hardware: bool
    locked_network_boundary: bool
    algorithm_evidence_complete: bool


@dataclass(frozen=True)
class AcceptanceResult:
    passed: bool
    reason: str
    details: dict = field(default_factory=dict)


def p95(values: list[float]) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


class SystemAcceptanceGate:
    def evaluate_m1(self, inputs: AcceptanceInputs) -> AcceptanceResult:
        missing = [unit for unit in [f"U{i}" for i in range(0, 6)] if not inputs.unit_results.get(unit)]
        if missing:
            return AcceptanceResult(False, "M1 缺少通过单元: " + ",".join(missing))
        return AcceptanceResult(True, "M1 平台模拟闭环准入通过")

    def evaluate_u7(self, inputs: AcceptanceInputs) -> AcceptanceResult:
        blockers: list[str] = []
        missing = [unit for unit in [f"U{i}" for i in range(0, 7)] if not inputs.unit_results.get(unit)]
        if missing:
            blockers.append("U0-U6 未全部完成: " + ",".join(missing))
        if not inputs.algorithm_evidence_complete:
            blockers.append("14 算法真实验收证据不完整")
        if not inputs.locked_external_interfaces:
            blockers.append("外部生产接口未锁定")
        if not inputs.locked_domestic_hardware:
            blockers.append("国产 AI 加速卡未锁定")
        if not inputs.locked_network_boundary:
            blockers.append("网络边界策略未锁定")
        if blockers:
            return AcceptanceResult(False, "；".join(blockers))
        return AcceptanceResult(True, "U7 系统级生产验收准入通过")

    def check_realtime_analysis(self, latencies_ms: list[int], failures: int) -> AcceptanceResult:
        total = len(latencies_ms) + failures
        failure_rate = failures / total if total else 0
        latency_p95 = p95(latencies_ms)
        if latency_p95 > 3000:
            return AcceptanceResult(
                False,
                "实时分析 P95 超过 3 秒",
                {"p95_ms": latency_p95, "failure_rate": failure_rate},
            )
        if failure_rate >= 0.01:
            return AcceptanceResult(
                False,
                "实时分析失败率不小于 1%",
                {"p95_ms": latency_p95, "failure_rate": failure_rate},
            )
        return AcceptanceResult(
            True,
            "实时分析指标通过",
            {"p95_ms": latency_p95, "failure_rate": failure_rate},
        )
