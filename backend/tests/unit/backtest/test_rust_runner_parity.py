"""Rust BacktestRunner 与 Python BacktestLoop 结果 parity 测试。

同一策略 + 同一数据分别走两条编排路径（见 engine_service 的 runner 开关），
断言关键指标完全一致。两条路径共用 axon BacktestEngine，撮合 seed 配置与
逐 bar 顺序已对齐（见 axon-worker/src/backtest.rs 的 SEED_* 常量与顺序注释）。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from backtest.backtest_loop import BacktestLoop
from backtest.engine_service import EventDrivenBacktestService
from backtest.strategy_loader_service import StrategyLoaderService

# 覆盖有实际成交的策略模板（grid/cross_sectional/factor_timing/funding_arbitrage
# 依赖参数或因子/资金费，不在 Rust 放行子集内，不纳入本 parity 断言）
TEMPLATES = [
    "dual_ma",
    "momentum",
    "sma_crossover",
    "trend_follow",
    "mean_reversion",
    "mean_reversion_rl",
]


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


def _load(template: str):
    return StrategyLoaderService.load_strategy(
        strategy_name=template,
        strategy_params={},
        instrument_ids=[{"symbol": "BTCUSDT", "venue": "BINANCE"}],
        bar_types=["1h"],
    )


@pytest.mark.parametrize("template", TEMPLATES)
def test_rust_runner_matches_python_loop(template: str, zigzag_kline: pd.DataFrame) -> None:
    """Rust BacktestRunner 与 Python BacktestLoop 在同一输入下产出完全一致的结果。"""
    py_strategy = _load(template)
    rust_strategy = _load(template)
    assert py_strategy is not None and rust_strategy is not None

    py_res = BacktestLoop(initial_cash=100_000.0).run(py_strategy, zigzag_kline, symbol="BTCUSDT")

    svc = EventDrivenBacktestService(data_provider=None)  # _run_rust_single 不使用 provider
    rust_res = svc._run_rust_single(rust_strategy, zigzag_kline, "BTCUSDT", 100_000.0)

    assert rust_res.fills == py_res.fills
    assert rust_res.orders_accepted == py_res.orders_accepted
    assert rust_res.orders_rejected == py_res.orders_rejected
    assert len(rust_res.trade_records) == len(py_res.trade_records)
    assert rust_res.total_pnl == pytest.approx(py_res.total_pnl, abs=1e-6)
    assert rust_res.final_nav == pytest.approx(py_res.final_nav, abs=1e-6)
    assert rust_res.max_drawdown == pytest.approx(py_res.max_drawdown, abs=1e-6)
    # 逐 bar NAV 曲线点数一致
    assert len(rust_res.equity_curve) == len(py_res.equity_curve)


def test_default_runner_uses_rust(zigzag_kline: pd.DataFrame, monkeypatch) -> None:
    """默认（engine_config 不传 runner）时，可放行子集应走 Rust 路径。"""
    calls = _spy_rust_calls(monkeypatch)
    svc = EventDrivenBacktestService(data_provider=_StubProvider(zigzag_kline))
    svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        engine_config={},
    )
    assert calls["n"] == 1


def test_python_runner_opt_out(zigzag_kline: pd.DataFrame, monkeypatch) -> None:
    """显式 runner='python' 时应回退到 Python BacktestLoop。"""
    calls = _spy_rust_calls(monkeypatch)
    svc = EventDrivenBacktestService(data_provider=_StubProvider(zigzag_kline))
    svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        engine_config={"runner": "python"},
    )
    assert calls["n"] == 0


class _StubProvider:
    """最小 provider：仅提供单品种单周期 K 线，供 run_backtest 分支测试。"""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def load_multiple(self, **_kwargs):
        return {"BTCUSDT_1h": self._df.copy()}, None


def _spy_rust_calls(monkeypatch) -> dict:
    """包装 _run_rust_single，记录被调用次数。"""
    calls = {"n": 0}
    orig = EventDrivenBacktestService._run_rust_single

    def spy(self, *args, **kwargs):
        calls["n"] += 1
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(EventDrivenBacktestService, "_run_rust_single", spy)
    return calls
