"""研究场景抽象（PRD §5.4）。

P0 只抽 4 个真实会变化的点：describe / build_tasks / evaluate / promote。
P2 接 strategy 场景时实测发现，生成/修复 prompt、指标提取、OOS 口径、采纳
硬门同样是场景特定的——这批环节以「可选钩子默认实现」的形式收进
scenarios/base.ScenarioDefaults（factor 继承即行为不变），loop 通过场景对象调用。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ResearchScenario(Protocol):
    """场景协议：决定候选是什么、怎么评估、产物落到哪。

    四个必选方法之外，场景还可选择性覆写 ScenarioDefaults 中的钩子：
    generate_hypothesis / render_context / data_note / code_prompt /
    generate_code / repair_code / build_feedback / metrics_from_analysis /
    oos_metrics / judge。
    """

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
    if name == "strategy":
        from research.scenarios.strategy import StrategyScenario

        return StrategyScenario()
    raise LookupError(f"场景 {name} 暂未实现")
