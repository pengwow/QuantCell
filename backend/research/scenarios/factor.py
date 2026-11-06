"""factor 场景实现：候选 = 因子代码，评估 = FactorService，产物 = 因子库。

P0 只做 P0 已有的能力：评估直接委托 `FactorService.analyze_code_panel`
（沙箱执行在 service 内部走 FactorSandbox），不在这里重复实现指标计算。
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from factor.engine import UNSUPPORTED_FACTORS, code_hash
from factor.models import FactorCatalog
from factor.service import FactorService, get_factor_service
from research import agents, consts, service
from research.scenarios.base import ScenarioDefaults
from utils.db_session import get_db_session


def rank_corr(a: Any, b: Any, *, min_samples: int = 50) -> float | None:
    """两个面板/序列的 Spearman 秩相关；样本不足或缺失返回 None。

    口径是“池化”：把 (datetime, symbol) 对齐后所有行一起算秩相关，
    不是逐品种算完再平均——多品种下避免少数品种样本量差异主导结果。
    """
    if a is None or b is None:
        return None
    left, right = pd.Series(a), pd.Series(b)
    joined = pd.concat([left.rank(), right.rank()], axis=1, join="inner").dropna()
    if len(joined) < min_samples:
        return None
    return float(joined.iloc[:, 0].corr(joined.iloc[:, 1], method="spearman"))


def load_seed_factor(name: str) -> dict[str, Any] | None:
    """按名称查种子因子（PRD §6.2「基于此因子研究」入口），不存在返回 None。

    只读取展示用的最小字段：描述、代码（code/expression 通用兜底）、最近指标摘要。
    """
    with get_db_session() as db:
        row = db.query(FactorCatalog).filter(FactorCatalog.name == name).first()
        if row is None:
            return None
        metrics: Any = None
        if row.last_metrics:
            try:
                metrics = json.loads(row.last_metrics)
            except ValueError:
                metrics = None
        return {
            "name": row.name,
            "description": row.description or "",
            "code": (row.code or row.expression or "").strip(),
            "metrics": metrics if isinstance(metrics, dict) else None,
        }


def seed_context(seed: dict[str, Any]) -> str:
    """把种子因子渲染成 propose 上下文附页：说明 + 指标 + 代码给到 LLM。"""
    lines = [f"\n\n种子因子：{seed['name']}", f"- 说明：{seed['description'] or '（无描述）'}"]
    metrics = seed.get("metrics") or {}
    # 只取数值型指标前 8 项，避免 snapshot 的非数值字段把 prompt 撑爆
    summary = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:8] if isinstance(v, (int, float)))
    if summary:
        lines.append(f"- 最近指标：{summary}")
    if seed.get("code"):
        lines.append(f"- 代码（以此为基础做条件化改进，不要原样照抄）：\n```python\n{seed['code']}\n```")
    return "\n".join(lines)


class FactorScenario(ScenarioDefaults):
    """factor 场景：把研究候选当作待入库的因子代码。

    生成/指标/硬门的 factor 默认行为继承 ScenarioDefaults（P2 起 loop 改为
    调用场景对象上的钩子，本类无需自己定义）。
    """

    key = "factor"

    def __init__(self, service: FactorService | None = None):
        # 单例而非 new：采纳写库后 factor 路由的内存缓存必须立即可见，否则
        # 因子库列表（查 DB）有、代码 Tab/计算（走内存）404
        self.service = service or get_factor_service()
        # 因子库参考面板按原始行情缓存一次，供所有 trial 复用
        self._library_panels: list[pd.Series] | None = None

    def describe(self, cfg: dict[str, Any]) -> str:
        return (
            f"场景：因子挖掘。数据：{','.join(cfg.get('symbols') or [])} "
            f"{cfg.get('interval', '1h')} {cfg.get('start')}~{cfg.get('end')}。"
            "评估口径：截面 IC / IC_IR + 样本外方向一致性 + 与现有因子的截面秩相关。"
        )

    def build_tasks(
        self,
        *,
        llm_call,
        hypothesis: str,
        context: str,
        n: int,
    ) -> tuple[list[Any], dict[str, Any]]:
        # 复用自研的 plan 提示词；场景只决定“取几条”，不另写一套 prompt
        tasks, usage = agents.plan_tasks(llm_call, hypothesis, context)
        return tasks[: max(int(n), 1)], usage

    def evaluate(self, code: str, raw_map: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        return self.service.analyze_code_panel(
            code,
            raw_map,
            interval=cfg.get("interval", "1h"),
            label="research_trial",
            test_ratio=float(cfg.get("test_ratio") or 0.0),
            wf_folds=int(cfg.get("wf_folds") or 0),
        )

    def promote(self, trial: dict[str, Any]) -> str:
        """把 trial 代码写入因子库（PRD §2.1「采纳」）。

        幂等：
        - trial 已记录 promoted_factor_name → 直接返回；
        - 同名或同代码的代码因子已存在 → 复用既有因子名，只补 provenance。
        provenance.source 保留原取值（首次为 research），再追加 session_id / trial_id。
        """
        code = str(trial.get("code") or "").strip()
        if not code:
            raise ValueError("trial 没有可入库的代码")
        session_id, trial_id = int(trial["session_id"]), int(trial["id"])
        already = trial.get("promoted_factor_name")
        if already:
            return str(already)

        digest = code_hash(code)
        name = f"rs_{session_id}_{trial_id}"
        with get_db_session() as db:
            existing = (
                db.query(FactorCatalog)
                .filter(FactorCatalog.kind == "code")
                .filter((FactorCatalog.name == name) | (FactorCatalog.code_hash == digest))
                .first()
            )
        target = existing.name if existing is not None else name
        prev = {}
        if existing is not None and existing.provenance:
            try:
                prev = json.loads(existing.provenance)
            except TypeError, ValueError:
                prev = {}
        provenance = {
            **prev,
            # 保留既有 source，避免把历史来源（如 quick 挖掘）改写成 research
            "source": prev.get("source") or "research",
            "session_id": session_id,
            "trial_id": trial_id,
        }
        description = (existing.description if existing is not None else trial.get("hypothesis")) or ""
        # 复用既有因子入库路径（名称校验 / 沙箱执行 / code_hash 去重都在里面）
        self.service.save_code_factor(target, code, description=description, provenance=provenance)
        with get_db_session() as db:
            service.update_trial(db, trial_id, promoted_factor_name=target)
        return target

    def library_corr(self, series: Any, raw_map: dict[str, Any]) -> float | None:
        """与因子库参考因子的最大 |秩相关|（无参考因子时返回 None）。

        取“最坏情况”而不是平均：只要有一个参考因子与候选高度相关，
        就应当判冗余。每个参考因子内部同样是池化秩相关（见 rank_corr）。
        """
        if series is None:
            return None
        panels = self._ensure_library_panels(raw_map)
        if not panels:
            return None
        corrs = [rank_corr(series, p) for p in panels]
        values = [abs(c) for c in corrs if c is not None]
        return max(values) if values else None

    def _ensure_library_panels(self, raw_map: dict[str, Any]) -> list[pd.Series]:
        if self._library_panels is not None:
            return self._library_panels
        panels: list[pd.Series] = []
        names = [n for n in self.service.get_factor_list() if n not in UNSUPPORTED_FACTORS]
        for name in names[: consts.LIBRARY_CORR_MAX_FACTORS]:
            try:
                panels.append(self.service._panel_from_raw(name, raw_map))
            except Exception:
                # 单个因子不可计算（数据不足等）不应阻断硬门，跳过即可
                continue
        self._library_panels = panels
        return panels
