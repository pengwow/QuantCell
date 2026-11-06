"""strategy 场景实现：候选 = 策略代码（BaseStrategy 子类），评估 = 统一回测内核，产物 = 策略库。

PRD §5.4 / P2 里程碑：第二个 scenario 接入 deep 闭环，不改会话/trial 表。
评估复用生产回测路径（EventDrivenBacktestService._run_rust_single，runner 默认
kernel），多品种独立资金池，与回测页口径一致。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from research import agents, consts, service
from research.scenarios.base import ScenarioDefaults
from strategy.base import BaseStrategy
from strategy.service import StrategyService
from utils.db_session import get_db_session

# 训练段最少 bar 数：低于该值策略连最基本的指标都算不稳，直接判数据不足
MIN_TRAIN_BARS = 60
# 测试段最少 bar 数：样本外段太短时 flag 记 None（不做 OOS 判定）而不是硬报错
MIN_TEST_BARS = 20

STRATEGY_HYPOTHESIS_SYSTEM = (
    "你是资深量化策略研究员。基于研究历史与数据说明，提出一条下一步要尝试的策略假设，"
    "说明为什么在当前进度下值得试（避免重复已失败的方向）。只输出 JSON："
    '{"hypothesis": "...", "reason": "...", "prediction": "..."}'
)

STRATEGY_PLAN_SYSTEM = (
    "你是量化策略生成器。根据假设提出 n 个具体的交易策略任务，"
    "entry/exit 规则写清楚（指标、阈值、仓位），彼此拉开差异。"
    "只输出 JSON 数组，元素字段 name/description/formulation/params。"
)

STRATEGY_CODE_SYSTEM = (
    "你编写单品种交易策略代码。约束：\n"
    "1. 只输出一个 Python 代码块，定义一个继承 strategy.base.BaseStrategy 的策略类；\n"
    "2. __init__(self, config)：config 是 strategy.base.StrategyConfig，"
    "通过 config.symbol 取品种；\n"
    "3. 实现 on_bar(self, bar, ctx)，返回 axon 的 Action"
    "（from axon_quant import Action, ActionType）；\n"
    "4. 不访问网络/文件，不使用未来数据，所有状态保存在 self；\n"
    "5. 指标手算（滚动窗口用列表切片），不 import pandas/numpy。\n"
    "只输出 Python 代码块。"
)

STRATEGY_FEEDBACK_SYSTEM = (
    "你是量化策略评审。结合研究历史与本轮回测（夏普/收益/回撤/胜率/成交数），"
    "给出下一步：继续打磨当前假设，还是换方向。只输出 JSON："
    '{"observations": "...", "evaluation": "...", "new_hypothesis": "...", "reason": "..."}'
)


class StrategyTask(BaseModel):
    """deep 闭环的策略候选任务规格。"""

    name: str = Field(default="strategy", max_length=80)
    description: str = Field(min_length=1, max_length=600)
    formulation: str = Field(default="", max_length=2000)
    params: dict[str, float] = Field(default_factory=dict)


def _extract_json(content: str) -> Any:
    """从 LLM 输出抽取 JSON（容忍 ```json 包裹与前后缀文字），失败抛 ValueError。"""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # 起始符决定结束符：数组取最后一个 ]、对象取最后一个 }，否则数组会被截成缺右括号的残片
    if text.find("[") >= 0 and (text.find("{") < 0 or text.find("[") < text.find("{")):
        start = text.find("[")
        return json.loads(text[start : text.rfind("]") + 1])
    start = text.find("{")
    if start < 0:
        raise ValueError("LLM 输出中没有 JSON")
    return json.loads(text[start : text.rfind("}") + 1])


class StrategyScenario(ScenarioDefaults):
    """strategy 场景：候选是策略，评估走回测，采纳落策略库（backend/strategies）。"""

    key = "strategy"

    # ---- 场景协议：describe / build_tasks / evaluate / promote ----

    def describe(self, cfg: dict[str, Any]) -> str:
        return (
            f"场景：策略挖掘。数据：{','.join(cfg.get('symbols') or [])} "
            f"{cfg.get('interval', '1h')}，窗口 {cfg.get('start')}~{cfg.get('end')}。"
            "评估口径：统一回测内核（夏普/累计收益/最大回撤/胜率/成交数），"
            f"样本外按 test_ratio={cfg.get('test_ratio', consts.DEFAULT_TEST_RATIO)} 时间切分。"
        )

    def build_tasks(
        self, *, llm_call, hypothesis: str, context: str, n: int
    ) -> tuple[list[StrategyTask], dict[str, Any]]:
        user = f"假设：{hypothesis}\n\n上下文：\n{context}\n\n请提出 {max(int(n), 1)} 个策略任务（JSON 数组）。"
        content, usage = llm_call(STRATEGY_PLAN_SYSTEM, user, stage="plan")
        data = _extract_json(content)
        items = data if isinstance(data, list) else data.get("tasks", [])
        tasks: list[StrategyTask] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                tasks.append(
                    StrategyTask(
                        name=str(item.get("name") or "strategy")[:80],
                        description=str(item.get("description") or ""),
                        formulation=str(item.get("formulation") or "")[:2000],
                        params={str(k): float(v) for k, v in (item.get("params") or {}).items()},
                    )
                )
            except TypeError, ValueError:
                # 单条任务坏了不影响其余候选
                continue
        return tasks[: max(int(n), 1)], usage

    def evaluate(self, code: str, raw_map: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        cls = self._load_strategy_class(code)
        interval = str(cfg.get("interval") or "1h")
        init_cash = float(cfg.get("initial_cash") or consts.DEFAULT_STRATEGY_INITIAL_CASH)
        test_ratio = float(cfg.get("test_ratio") or 0.0)

        from backtest.backtest_loop import clean_ohlcv_df
        from backtest.engine_service import EventDrivenBacktestService

        # provider 只服务"从数据源取数"的路径；这里数据已就位，逐段直跑内核不走它
        engine = EventDrivenBacktestService(None)
        per_symbol: dict[str, Any] = {}
        for sym, df in (raw_map or {}).items():
            cleaned = clean_ohlcv_df(df)
            total = len(cleaned)
            cut = int(total * (1 - test_ratio)) if test_ratio > 0 else total
            if cut < MIN_TRAIN_BARS:
                raise ValueError(f"品种 {sym} 训练段只有 {cut} 根 bar（至少 {MIN_TRAIN_BARS}），请加长数据窗口")
            entry: dict[str, Any] = {
                "train": self._run_segment(engine, cls, cleaned.iloc[:cut], sym, interval, init_cash)
            }
            if test_ratio > 0 and total - cut >= MIN_TEST_BARS:
                entry["test"] = self._run_segment(engine, cls, cleaned.iloc[cut:], sym, interval, init_cash)
            per_symbol[sym] = entry
        if not per_symbol:
            raise ValueError("没有可用的行情数据")

        train = self._aggregate({sym: e["train"] for sym, e in per_symbol.items()})
        analysis: dict[str, Any] = {
            "train": train,
            "per_symbol": per_symbol,
            # 不返回 train_factor：策略没有因子序列，loop 的因子相关性去重会自动跳过
        }
        test = self._aggregate({sym: e["test"] for sym, e in per_symbol.items() if "test" in e})
        if test is not None:
            analysis["test"] = test
        return analysis

    def promote(self, trial: dict[str, Any]) -> str:
        """采纳 trial：代码写入策略库（backend/strategies/rs_<sid>_<tid>.py），幂等。

        沙箱/越权不必再查——code 在 evaluate 阶段已真实执行过；入库时补 provenance
        头注释（策略文件是纯 .py，没有 JSON 元数据位）。
        """
        code = str(trial.get("code") or "").strip()
        if not code:
            raise ValueError("trial 没有可入库的代码")
        already = trial.get("promoted_factor_name")
        if already:
            return str(already)
        name = f"rs_{int(trial['session_id'])}_{int(trial['id'])}"
        header = (
            f"# 来源：研究会话 trial={trial['id']}（scenario=strategy 自动采纳）\n"
            f"# 假设：{str(trial.get('hypothesis') or '')[:200]}\n\n"
        )
        StrategyService().save_strategy(name, header + code)
        with get_db_session() as db:
            service.update_trial(db, int(trial["id"]), promoted_factor_name=name)
        return name

    # ---- 场景钩子覆写（默认实现见 scenarios/base.py） ----

    def generate_hypothesis(self, llm_call, context: str, seed_factor: str | None):
        extra = f"\n\n种子策略方向（从该策略起步）：{seed_factor}" if seed_factor else ""
        content, usage = llm_call(STRATEGY_HYPOTHESIS_SYSTEM, context + extra, stage="propose")
        try:
            data = _extract_json(content)
            return agents.HypothesisOut(**data), usage
        except ValueError:
            # LLM 输出不可解析：给一条确定的兜底假设而不是中断整轮
            return agents.HypothesisOut(hypothesis="探索趋势跟随策略", reason="LLM 输出不可解析，使用兜底假设"), usage

    def build_feedback(self, llm_call, context: str, metrics: dict[str, Any], sota_metrics):
        user = (
            f"{context}\n\n本轮回测指标：{json.dumps(metrics, ensure_ascii=False, default=str)}\n"
            f"当前 SOTA：{json.dumps(sota_metrics or {}, ensure_ascii=False, default=str)}"
        )
        content, usage = llm_call(STRATEGY_FEEDBACK_SYSTEM, user, stage="feedback")
        try:
            return agents.FeedbackOut(**_extract_json(content)), usage
        except ValueError:
            return agents.FeedbackOut(evaluation="LLM 输出不可解析", reason=""), usage

    def code_prompt(self, task: StrategyTask) -> tuple[str, str]:
        user = (
            f"策略名称：{task.name}\n策略意图：{task.description}\n"
            f"规则细化：{task.formulation or '（自拟合理的 entry/exit 规则）'}\n"
            f"建议参数：{json.dumps(task.params, ensure_ascii=False)}\n请只输出 Python 代码块。"
        )
        return STRATEGY_CODE_SYSTEM, user

    def generate_code(self, llm_call, task: StrategyTask) -> tuple[str, dict[str, Any]]:
        system, user = self.code_prompt(task)
        content, usage = llm_call(system, user, stage="code")
        return agents.extract_code(content), usage

    def repair_code(self, llm_call, task: StrategyTask, code: str, kind: str, error: str) -> tuple[str, dict[str, Any]]:
        system, user = self.code_prompt(task)
        user += (
            f"\n\n上一版代码执行失败（{kind}）：{str(error)[:300]}\n\n"
            f"上一版代码：\n```python\n{code[:4000]}\n```\n"
            "返修要求：保持策略意图，修复上述问题后输出完整代码（仍只输出一个 Python 代码块）。"
        )
        content, usage = llm_call(system, user, stage="code")
        return agents.extract_code(content), usage

    def metrics_from_analysis(self, analysis: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
        return dict(analysis["train"])

    def oos_metrics(
        self, analysis: dict[str, Any], metrics: dict[str, Any], cfg: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """样本外口径：test 段独立回测的夏普对比样本内（ok/sign_flip/weak）。"""
        test = analysis.get("test")
        if not test:
            return None, None, "未启用样本外段（test_ratio=0 或数据不足）"
        train_sharpe = float(metrics.get("sharpe_ratio") or 0.0)
        test_sharpe = float(test.get("sharpe_ratio") or 0.0)
        metrics_oos = {k: v for k, v in test.items() if isinstance(v, (int, float))}
        if test_sharpe <= 0:
            flag = "sign_flip"
        elif train_sharpe > 0 and test_sharpe < 0.3 * train_sharpe:
            flag = "weak"
        else:
            flag = "ok"
        return metrics_oos, flag, f"test_sharpe={test_sharpe:.2f} vs train={train_sharpe:.2f}"

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
        """策略硬门：夏普 ≥ 下限、样本内盈利、成交数达标、样本外不翻转。

        oos_flag 为 None（未启用样本外段）不拦截，只记录——策略与因子不同，
        不强制要求 OOS 段。corr_* 参数与策略门无关，保留签名以匹配 loop 调用。
        """
        cfg = cfg or {}
        floor = float(cfg.get("sharpe_floor") or consts.DEFAULT_STRATEGY_SHARPE_FLOOR)
        min_trades = int(cfg.get("min_trades") or consts.DEFAULT_STRATEGY_MIN_TRADES)
        sharpe = metrics.get("sharpe_ratio")
        pnl = metrics.get("total_pnl")
        trades = metrics.get("trades")
        gates = {
            "sharpe": {"pass": sharpe is not None and float(sharpe) >= floor, "value": sharpe, "floor": floor},
            "pnl": {"pass": pnl is not None and float(pnl) > 0, "value": pnl},
            "trades": {
                "pass": trades is not None and int(trades or 0) >= min_trades,
                "value": trades,
                "floor": min_trades,
            },
            "oos": {"pass": oos_flag in (None, "ok"), "value": oos_flag},
        }
        failed = [name for name, g in gates.items() if not g["pass"]]
        decision = not failed
        return {
            "decision": decision,
            "gates": gates,
            "reason": "策略硬门全部通过" if decision else "未通过：" + "、".join(failed),
        }

    # ---- 内部工具 ----

    def _load_strategy_class(self, code: str) -> type:
        """从代码字符串加载策略类：落临时模块导入，找 BaseStrategy 子类。"""
        module_name = "rs_candidate_strategy"
        with tempfile.TemporaryDirectory(prefix="rs_strategy_") as tmp:
            path = Path(tmp) / f"{module_name}.py"
            path.write_text(code, encoding="utf-8")
            spec = importlib.util.spec_from_file_location(module_name, path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            # 显式注册 sys.modules：候选代码内部可能 import 自己所在包/触发重入
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                sys.modules.pop(module_name, None)

        candidates = [
            attr
            for attr in vars(module).values()
            if isinstance(attr, type)
            and issubclass(attr, BaseStrategy)
            and attr is not BaseStrategy
            and attr.__module__ == module_name
        ]
        if not candidates:
            raise ValueError("代码里没有找到 BaseStrategy 子类")
        return candidates[0]

    def _run_segment(
        self,
        engine: Any,
        strategy_cls: type,
        df: Any,
        symbol: str,
        interval: str,
        init_cash: float,
    ) -> dict[str, Any]:
        """在一段行情上跑回测（内核路径），返回指标摘要 dict。"""
        from backtest.strategy_loader_service import StrategyLoaderService

        strategy = StrategyLoaderService._instantiate_strategy(
            strategy_cls,
            {},
            instrument_ids=[{"symbol": symbol}],
            bar_types=[f"{symbol}-{interval}"],
        )
        result = engine._run_rust_single(strategy, df, symbol, init_cash, interval=interval)
        return {
            "sharpe_ratio": float(result.sharpe_ratio or 0.0),
            "total_pnl": float(result.total_pnl or 0.0),
            "final_nav": float(result.final_nav or 0.0),
            "max_drawdown": float(result.max_drawdown or 0.0),
            "max_drawdown_pct": float(result.max_drawdown_pct or 0.0),
            "win_rate": float(result.win_rate or 0.0),
            "trades": int(result.fills or 0),
            "total_fees": float(result.total_fees or 0.0),
            "bar_count": int(result.bar_count or 0),
        }

    def _aggregate(self, per_symbol: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        """多品种独立资金池聚合：夏普/胜率/终值取均值，盈亏/费用累加，回撤取最大。

        与 run_backtest 多品种语义一致（每品种独立跑内核，跨品种聚合在 Python 侧）。
        """
        if not per_symbol:
            return None
        agg: dict[str, Any] = {
            k: sum(float(e.get(k) or 0.0) for e in per_symbol.values()) / len(per_symbol)
            for k in ("sharpe_ratio", "win_rate", "final_nav")
        }
        for k in ("max_drawdown", "max_drawdown_pct"):
            agg[k] = max(float(e.get(k) or 0.0) for e in per_symbol.values())
        for k in ("total_pnl", "total_fees", "trades", "bar_count"):
            agg[k] = sum(e.get(k) or 0 for e in per_symbol.values())
        return agg
