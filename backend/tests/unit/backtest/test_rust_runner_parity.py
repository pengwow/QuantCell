"""Rust BacktestRunner 与 Python BacktestLoop 结果 parity 测试。

同一策略 + 同一数据分别走两条编排路径，断言关键指标一致。
两条路径共用 axon BacktestEngine，撮合 seed 配置与逐 bar 顺序已对齐
（见 axon-worker/src/backtest.rs 的 SEED_* 常量与 begin_bar/rebalance 顺序注释）。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from axon_quant import Action

from backtest.backtest_loop import BacktestLoop
from backtest.engine_service import EventDrivenBacktestService
from strategy.base import BaseStrategy, StrategyConfig


@pytest.fixture
def zigzag_kline() -> pd.DataFrame:
    """正弦震荡行情：价格反复穿越均线 → 策略反复换仓，覆盖开/平仓路径。"""
    n = 200
    dates = pd.date_range("2024-07-01", periods=n, freq="1h")
    closes = [100.0 + 20.0 * math.sin(i / 5.0) for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=dates,
    )


class _SmaToggle(BaseStrategy):
    """close 上穿/下穿 10 周期均线 → 满仓 buy / 空仓 sell。"""

    def __init__(self) -> None:
        super().__init__(StrategyConfig(name="sma_toggle", symbol="BTCUSDT", position_limit=1.0))

    def on_bar(self, bar, ctx=None):
        ctx.closes.append(bar["close"])
        period = 10
        if len(ctx.closes) < period:
            return Action(
                action_type="hold", confidence=0.0, target_position=0.0, model_id="sma_toggle", inference_time_us=0
            )
        ma = sum(ctx.closes[-period:]) / period
        if bar["close"] > ma:
            return Action(
                action_type="buy", confidence=0.8, target_position=1.0, model_id="sma_toggle", inference_time_us=0
            )
        return Action(
            action_type="sell", confidence=0.8, target_position=0.0, model_id="sma_toggle", inference_time_us=0
        )


def test_rust_runner_matches_python_loop(zigzag_kline: pd.DataFrame) -> None:
    """Rust BacktestRunner 与 Python BacktestLoop 在同一输入下产出完全一致的结果。"""
    py_res = BacktestLoop(initial_cash=100_000.0).run(_SmaToggle(), zigzag_kline, symbol="BTCUSDT")

    svc = EventDrivenBacktestService(data_provider=None)  # _run_rust_single 不使用 provider
    rust_res = svc._run_rust_single(_SmaToggle(), zigzag_kline, "BTCUSDT", 100_000.0)

    assert rust_res.fills == py_res.fills
    assert rust_res.orders_accepted == py_res.orders_accepted
    assert rust_res.orders_rejected == py_res.orders_rejected
    assert len(rust_res.trade_records) == len(py_res.trade_records)
    assert rust_res.total_pnl == pytest.approx(py_res.total_pnl, abs=1e-6)
    assert rust_res.final_nav == pytest.approx(py_res.final_nav, abs=1e-6)
    assert rust_res.max_drawdown == pytest.approx(py_res.max_drawdown, abs=1e-6)
    # 逐 bar NAV 曲线点数一致
    assert len(rust_res.equity_curve) == len(py_res.equity_curve)
