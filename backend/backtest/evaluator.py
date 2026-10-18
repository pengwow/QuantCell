"""HPO 单 trial 评估器。

统一路径：每个 trial 用注入的 build_strategy 构造 BaseStrategy，
在传入的 DataFrame 上跑唯一 BacktestLoop，从 BacktestResult 取优化目标。

ponytail:HPO 有意保留 Python BacktestLoop（同 worker/lifecycle 的说明）——
参数搜索不需要 Rust 原生撮合，省去每 trial 的 DataFrame→bars 序列化；
部署回测仍走 Rust BacktestRunner，两者 parity 由 test_rust_runner_parity.py 守护。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from backtest.backtest_loop import BacktestLoop

logger = logging.getLogger(__name__)


class BacktestEvaluator:
    """把 BacktestLoop + 数据 + 策略工厂封装成 HPO 可消费的评估器。

    典型用法::

        evaluator = BacktestEvaluator(
            data=df,
            symbol="BTCUSDT",
            build_strategy=_build_strategy,   # (params) -> BaseStrategy
            param_space={"fast": (3, 10), "slow": (15, 40)},
        )

        # 用法一：HPORunner —— objective_fn 传 evaluate，param_space 用
        #   {"type": "int", "low": 3, "high": 10} 格式（由 HPORunner 自己消费）
        # 用法二：optuna 原生 study —— study.optimize(evaluator.objective),
        #   param_space 用 (low, high) 元组格式（由 objective 消费）
    """

    def __init__(
        self,
        data: pd.DataFrame,
        symbol: str,
        build_strategy: Callable[[dict], object],
        param_space: dict,
        initial_cash: float = 100_000.0,
        metric: str = "sharpe_ratio",
    ):
        self._data = data
        self._symbol = symbol
        self._build_strategy = build_strategy
        self._param_space = param_space
        self._initial_cash = initial_cash
        self._metric = metric

    def evaluate(
        self,
        params: dict,
        report: Callable[[int, float], None] | None = None,
    ) -> float:
        """单次 trial 评估：跑 BacktestLoop → 上报中间值 → 返回目标指标。

        report 可选：跑完后从 equity_curve 逐点上报（与旧版 bar_nav_curve
        同源），供 HPORunner/optuna 记录 intermediate_values 与剪枝比较。
        ponytail: 事后上报，引擎支持 step 内 nav 查询后可升级为真·中途剪枝。
        """
        try:
            strategy = self._build_strategy(params)
            result = BacktestLoop(initial_cash=self._initial_cash).run(
                strategy=strategy, data=self._data, symbol=self._symbol
            )
        except Exception as e:
            logger.warning(f"回测评估失败 params={params}: {e}")
            return float("-inf")

        if report is not None:
            for step, point in enumerate(result.equity_curve):
                try:
                    report(step, float(point["equity"]))
                except Exception:
                    # 与旧版一致：单点上报失败（含剪枝信号）不中断评估
                    pass

        value = float(getattr(result, self._metric, 0.0) or 0.0)
        return value if value == value else 0.0  # NaN 防御

    def objective(self, trial) -> float:
        """optuna 原生协议：从 param_space（(low, high) 元组）采样并评估。"""
        params = {name: trial.suggest_int(name, int(rng[0]), int(rng[1])) for name, rng in self._param_space.items()}
        return self.evaluate(params)
