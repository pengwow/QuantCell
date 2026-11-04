"""研究场景抽象（PRD §5.4）。

只抽 4 个真实会变化的点：describe / build_tasks / evaluate / promote。
P0 只实现 factor；model / strategy 保持 Protocol 可容纳，不做实现。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ResearchScenario(Protocol):
    """场景协议：决定候选是什么、怎么评估、产物落到哪。"""

    key: str

    def describe(self, cfg: dict[str, Any]) -> str:
        """进 prompt 的背景 + 数据说明 + 评测口径。"""
        ...

    def build_tasks(
        self,
        *,
        llm_call: Callable[[str, str], tuple[str, dict[str, Any]]],
        hypothesis: str,
        context: str,
        n: int,
    ) -> tuple[list[Any], dict[str, Any]]:
        """生成候选任务（factor: 因子任务；model: 结构/超参变更）。"""
        ...

    def evaluate(self, code: str, raw_map: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        """评估候选，返回与 FactorService.analyze_code_panel 一致的评估结构。"""
        ...

    def promote(self, trial: Any) -> str:
        """采纳试验并落到目标库，返回产物名。"""
        ...


def get_scenario(name: str) -> ResearchScenario:
    """按 key 取场景实现；未实现的场景显式拒绝（禁止静默降级）。"""
    if name == "factor":
        # 延迟导入：scenarios.factor 依赖 factor.*，避免 research 包导入期拉起重依赖
        from research.scenarios.factor import FactorScenario

        return FactorScenario()
    raise LookupError(f"场景 {name} 暂未实现")
