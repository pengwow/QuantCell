"""BacktestEvaluator — 把真实回测引擎接进 HPO 闭环的胶水层。

架构:每 trial 创建全新 EventDrivenBacktestEngine → 注入策略参数 → run_backtest →
    从 RunResult.bar_nav_curve 逐点调 report → 返回目标指标。

引擎约束(必须知道):
- BacktestEngine.run() 必须整段跑完才能拿结果,无法中途 nav 查询 → report 是
  "事后上报"(跑完再逐点调),Optuna MedianPruner 收得到中间值记录,但 trial
  间比较剪枝仍有效(后续引擎暴露 step 内 nav 查询时,把 report 挪进 step 循环
  即可升级为真·中途剪枝)。
- 引擎 run() 过后 is_finished=True,不能复用,每 trial 必须 new。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backtest.engines.event_engine import EventDrivenBacktestEngine

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

# RunResult 可提取的目标指标 → 访问器
_METRIC_ACCESSORS: dict[str, Callable[[Any, float], float]] = {
    # (RunResult, initial_cash) -> value
    "return": lambda rr, cash: (rr.final_nav - cash) / cash if cash > 0 else rr.final_nav,
    "final_nav": lambda rr, _cash: rr.final_nav,
    "total_pnl": lambda rr, _cash: rr.total_pnl,
    "sharpe": lambda rr, _cash: rr.sharpe_ratio,
    "win_rate": lambda rr, _cash: rr.win_rate,
    "max_drawdown": lambda rr, _cash: -rr.max_drawdown_pct,  # 转成越大越好
    "profit_factor": lambda rr, _cash: rr.profit_factor if hasattr(rr, "profit_factor") else 0.0,
}


class BacktestEvaluator:
    """把 EventDrivenBacktestEngine + 数据 + instrument 封装成 HPO 可消费的 objective 工厂。

    典型用法::

        evaluator = BacktestEvaluator(
            csv_path="BTCUSDT_1h.csv",
            instrument_dict=swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0),
            instrument_id="BTCUSDT",
            engine_config={
                "initial_capital": 100_000.0,
                "start_date": "2025-01-01", "end_date": "2025-01-10",
                "half_spread": 0.001, "depth_levels": 4,
                "size_per_level": 50.0, "auto_rebalance_threshold": 0.001,
            },
            initial_cash=100_000.0,
        )

        def build_strategy(params):
            from strategies.dual_ma import DualMA, DualMAConfig
            return DualMA(DualMAConfig(
                instrument_ids=["BTCUSDT"], bar_types=["1h"],
                fast_period=int(params["fast"]), slow_period=int(params["slow"]),
            ))

        objective = evaluator.make_objective(build_strategy, metric="return")
        hpo.optimize(objective_fn=objective, param_space={...}, pruner_type="median")
    """

    def __init__(
        self,
        csv_path: str | Path,
        instrument_dict: dict[str, Any],
        instrument_id: str,
        engine_config: dict[str, Any],
        initial_cash: float | None = None,
        csv_sep: str = ",",
    ):
        self.csv_path = str(csv_path)
        self.instrument_dict = instrument_dict
        self.instrument_id = instrument_id
        self.engine_config = dict(engine_config)
        self.initial_cash = float(
            initial_cash if initial_cash is not None else self.engine_config.get("initial_capital", 100_000.0)
        )
        self.csv_sep = csv_sep

        # 引擎配置必需字段预检(提前暴露问题,别让 Optuna 在 trial 里才崩)
        required = {"initial_capital", "start_date", "end_date"}
        missing = required - set(self.engine_config.keys())
        if missing:
            raise ValueError(f"engine_config 缺少必需字段: {missing}")
        if not Path(self.csv_path).exists():
            raise FileNotFoundError(f"CSV 数据文件不存在: {self.csv_path}")

    def make_objective(
        self,
        strategy_builder: Callable[[dict[str, Any]], Any],
        metric: str = "return",
    ) -> Callable[[dict[str, Any], Callable[[int, float], None]], float]:
        """返回 HPO 目标函数:接收 params dict + report 闭包 → 目标指标值。

        Args:
            strategy_builder: (params) → strategy 实例,实例必须有 .on_start() / .on_bar() / .on_stop()
            metric: 目标指标名,支持: return / final_nav / total_pnl / sharpe / win_rate / max_drawdown / profit_factor

        Returns:
            objective_fn(params, report) -> float
        """
        accessor = _METRIC_ACCESSORS.get(metric)
        if accessor is None:
            raise ValueError(f"不支持的指标 {metric!r},可用: {list(_METRIC_ACCESSORS.keys())}")

        csv_path = self.csv_path
        ins_dict = self.instrument_dict
        engine_cfg = self.engine_config
        initial_cash = self.initial_cash
        csv_sep = self.csv_sep

        def evaluate(params: dict[str, Any], report: Callable[[int, float], None]) -> float:
            """单次 trial 评估:新建引擎 → 跑回测 → 上报中间值 → 返回目标指标。"""
            # 提前捕获非法参数(如 fast >= slow),避免浪费引擎启动时间
            if not self._validate_params(params):
                return float("-inf")

            engine = EventDrivenBacktestEngine(config=engine_cfg)
            try:
                engine.initialize()
                engine.add_venue("default", starting_capital=initial_cash)
                engine.add_instrument(ins_dict)
                engine.load_data_from_csv(csv_path, ins_dict, sep=csv_sep)

                strategy = strategy_builder(params)
                engine.add_strategy(strategy)

                # 跑完整个回测(Rust 引擎必须整段跑完才能拿结果)
                engine.run_backtest()
                rr = engine._engine.run()  # RunResult

                # 从 bar_nav_curve 逐点 report,让 Optuna 记录 intermediate values
                # ponytail:事后上报,引擎升级 step 内 nav 查询后可改为真·中途剪枝
                for step, (_ts_ns, nav) in enumerate(rr.bar_nav_curve):
                    try:
                        report(step, float(nav))
                    except Exception:
                        # Optuna 在 should_prune=True 时抛 TrialPruned,这里吃掉让上层处理
                        pass

                return float(accessor(rr, initial_cash))

            except Exception as e:
                logger.warning(f"回测评估失败 params={params}: {e}")
                return float("-inf")
            finally:
                # 引擎无显式 close,Python GC 会接管;此处清空引用帮助提前释放
                engine._strategies = []
                engine._dataframes = {}

        return evaluate

    # --- 子类/策略特定的参数合法性钩子(默认宽松,子类可 override) ---

    def _validate_params(self, params: dict[str, Any]) -> bool:
        """参数合法性预检,返回 False 时 objective 直接返回 -inf 跳过引擎启动。

        默认全放行,具体策略可 override 加规则(如 fast < slow)。
        """
        return True
