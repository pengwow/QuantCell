"""场景默认实现基类（P2 随 strategy 场景引入）。

PRD §5.4 原本只抽 describe/build_tasks/evaluate/promote 四个点，实测发现
另一批环节也是场景特定的：生成/修复 prompt、指标提取、OOS 口径、采纳硬门——
它们之前以函数形式硬编码在 loop.py / agents.py 里（factor 语义）。

处理方式：把这些默认行为收进 ScenarioDefaults；FactorScenario 继承它
（行为不变），loop 改为通过场景对象调用。strategy 场景按需覆写。
"""

from __future__ import annotations

from typing import Any

from research import agents, consts


class ScenarioDefaults:
    """可选钩子的 factor 默认实现。子类覆写时需保持 loop 侧的调用签名。"""

    key = ""

    # ---- propose / context ----

    def generate_hypothesis(self, llm_call, context: str, seed_factor: str | None) -> tuple[Any, dict[str, Any]]:
        # 默认（factor）：沿用 agents 的假设提示词
        return agents.generate_hypothesis(llm_call, context, seed_factor)

    def render_context(
        self,
        trials: list[dict[str, Any]],
        sota_trial: dict[str, Any] | None,
        knowledge: list[dict[str, Any]] | None = None,
        data_note: str | None = None,
    ) -> str:
        return agents.render_context(trials, sota_trial, knowledge=knowledge, data_note=data_note)

    def data_note(self, raw_map: dict[str, Any], cfg: dict[str, Any], train_bars: int) -> str:
        """数据事实附页（默认 factor 口径：单品种执行、截面面板在 Python 侧拼）。"""
        return (
            f"- 品种数:{len(raw_map)}；周期:{cfg.get('interval') or '1h'}；"
            f"训练段约 {train_bars} 根 K 线\n"
            "- 代码按单品种执行（系统逐品种跑一遍再拼成截面面板），df 没有 code/date 列；"
            "不要用 np.concatenate / DataFrame.get / 跨品种拼接"
        )

    # ---- 代码生成与修复 ----

    def code_prompt(self, task: Any) -> tuple[str, str]:
        return agents.code_prompt(task)

    def generate_code(self, llm_call, task: Any) -> tuple[str, dict[str, Any]]:
        return agents.generate_code(llm_call, task)

    def repair_code(self, llm_call, task: Any, code: str, kind: str, error: str) -> tuple[str, dict[str, Any]]:
        return agents.repair_code(llm_call, task, code, kind, error)

    # ---- 反馈 ----

    def build_feedback(
        self, llm_call, context: str, metrics: dict[str, Any], sota_metrics: dict[str, Any] | None
    ) -> tuple[Any, dict[str, Any]]:
        return agents.build_feedback(llm_call, context, metrics, sota_metrics)

    # ---- 评估后指标加工（factor 口径：IC/ICIR + WF 折 + 相关性）----

    def metrics_from_analysis(self, analysis: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        # 函数内导入：factor.llm_miner 是重依赖（pandas 面板栈），保持 research
        # 包导入期不拉起（scenario.py 的既有约定）
        from factor.llm_miner import _metrics_from_analysis

        return _metrics_from_analysis(analysis["train"])

    def oos_metrics(
        self, analysis: dict[str, Any], metrics: dict[str, Any], cfg: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None, str | None]:
        """返回 (样本外指标, flag, note)；flag ∈ ok / sign_flip / weak / None。"""
        from factor.llm_miner import _oos_metrics

        metrics_oos, flag, note, _folds = _oos_metrics(analysis, metrics, float(cfg.get("test_ratio") or 0.0))
        return metrics_oos, flag, note

    # ---- 采纳硬门（factor 口径）----

    def judge(
        self,
        *,
        metrics: dict[str, Any],
        oos_flag: str | None,
        corr_sota: float | None = None,
        corr_library: float | None = None,
        cfg: dict[str, Any] | None = None,
        sota_expected: bool = False,
    ) -> dict[str, Any]:
        cfg = cfg or {}
        from research.judge import evaluate_gates

        return evaluate_gates(
            ic_ir=metrics.get("ic_ir"),
            oos_flag=oos_flag,
            corr_vs_sota=corr_sota,
            corr_vs_library=corr_library,
            icir_floor=cfg.get("icir_floor") or consts.DEFAULT_ICIR_FLOOR,
            corr_threshold=cfg.get("corr_threshold") or consts.DEFAULT_CORR_THRESHOLD,
            sota_expected=sota_expected,
        )
