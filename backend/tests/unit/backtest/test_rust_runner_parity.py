"""Rust BacktestRunner 与 Python BacktestLoop 结果 parity 测试。

同一策略 + 同一数据分别走两条编排路径（见 engine_service 的 runner 开关），
断言关键指标完全一致。两条路径共用 axon BacktestEngine，撮合 seed 配置与
逐 bar 顺序已对齐（见 axon-worker/src/backtest.rs 的 SEED_* 常量与顺序注释）。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from axon_quant import Action

from backtest.backtest_loop import BacktestLoop
from backtest.engine_service import EventDrivenBacktestService
from backtest.strategy_loader_service import StrategyLoaderService
from strategy.base import BaseStrategy, StrategyConfig

# 覆盖有实际成交的模板（grid/cross_sectional 依赖具体参数/横截面 rank，
# 默认参数下不成交，不纳入本断言；因子/期货场景见下方专用用例）
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

    _assert_parity(py_res, rust_res)


def _assert_parity(py_res, rust_res) -> None:
    """两条路径关键指标必须完全一致。"""
    assert rust_res.fills == py_res.fills
    assert rust_res.orders_accepted == py_res.orders_accepted
    assert rust_res.orders_rejected == py_res.orders_rejected
    assert len(rust_res.trade_records) == len(py_res.trade_records)
    assert rust_res.total_pnl == pytest.approx(py_res.total_pnl, abs=1e-6)
    assert rust_res.final_nav == pytest.approx(py_res.final_nav, abs=1e-6)
    assert rust_res.max_drawdown == pytest.approx(py_res.max_drawdown, abs=1e-6)
    assert rust_res.total_fees == pytest.approx(py_res.total_fees, abs=1e-6)
    assert rust_res.win_rate == pytest.approx(py_res.win_rate, abs=1e-6)
    # 末态持仓一致
    assert rust_res.final_positions == py_res.final_positions
    # 逐 bar NAV 曲线点数一致
    assert len(rust_res.equity_curve) == len(py_res.equity_curve)


def _hold() -> Action:
    return Action(action_type="hold", confidence=0.0, target_position=0.0, model_id="x", inference_time_us=0)


class _BuyThenHold(BaseStrategy):
    """第 5 根 bar 起满仓买入（纯 OHLCV 驱动，不依赖因子）。"""

    def __init__(self) -> None:
        super().__init__(StrategyConfig(name="buy_hold", symbol="BTCUSDT", position_limit=1.0))
        self._n = 0

    def on_bar(self, bar, ctx=None):
        self._n += 1
        if self._n < 5:
            return _hold()
        return Action(action_type="buy", confidence=0.9, target_position=1.0, model_id="bh", inference_time_us=0)


class _FactorTiming(BaseStrategy):
    """因子阈值择时：v >= 0 买入，v < 0 清仓（读 ctx.features）。"""

    def __init__(self, factor_name: str = "mom") -> None:
        super().__init__(StrategyConfig(name="factor_timing", symbol="BTCUSDT", position_limit=1.0))
        self._factor_name = factor_name

    def on_bar(self, bar, ctx=None):
        ctx.closes.append(bar["close"])
        if not ctx.has_feature(self._factor_name):
            return _hold()
        if ctx.get_feature(self._factor_name) >= 0.0:
            return Action(action_type="buy", confidence=0.9, target_position=1.0, model_id="ft", inference_time_us=0)
        return Action(action_type="sell", confidence=0.9, target_position=0.0, model_id="ft", inference_time_us=0)


def _funding_frame(df: pd.DataFrame) -> pd.DataFrame:
    """逐 bar 资金费率（正负交替，mark 用 close）。"""
    rates = [0.0001 if i % 2 == 0 else -0.0002 for i in range(len(df))]
    return pd.DataFrame({"funding_rate": rates, "mark_price": df["close"].values}, index=df.index)


def _factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    """逐 bar 因子值（正弦，正负交替触发买卖）。"""
    return pd.DataFrame({"mom": [math.sin(i / 7.0) for i in range(len(df))]}, index=df.index)


@pytest.mark.parametrize(
    "trading_mode,funding,factor",
    [("spot", False, False), ("futures", True, False), ("spot", False, True), ("futures", True, True)],
)
def test_rust_runner_futures_and_factor_parity(
    trading_mode: str, funding: bool, factor: bool, zigzag_kline: pd.DataFrame
) -> None:
    """期货资金费结算 + 逐 bar 因子注入，两条路径结果一致。"""
    funding_df = _funding_frame(zigzag_kline) if funding else None
    feature_df = _factor_frame(zigzag_kline) if factor else None
    factory = (lambda: _FactorTiming("mom")) if factor else _BuyThenHold

    py_res = BacktestLoop(initial_cash=100_000.0).run(
        factory(),
        zigzag_kline,
        symbol="BTCUSDT",
        trading_mode=trading_mode,
        funding_df=funding_df,
        feature_dataframe=feature_df,
    )
    svc = EventDrivenBacktestService(data_provider=None)
    rust_res = svc._run_rust_single(
        factory(),
        zigzag_kline,
        "BTCUSDT",
        100_000.0,
        funding_df=funding_df,
        feature_dataframe=feature_df,
        futures=(trading_mode == "futures"),
    )
    _assert_parity(py_res, rust_res)


def test_default_runner_uses_rust(zigzag_kline: pd.DataFrame, monkeypatch) -> None:
    """默认（engine_config 不传 runner）时，可放行子集应走 Rust 路径。"""
    calls = _spy_rust_calls(monkeypatch)
    svc = EventDrivenBacktestService(data_provider=_StubProvider({"BTCUSDT_1h": zigzag_kline}))
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
    svc = EventDrivenBacktestService(data_provider=_StubProvider({"BTCUSDT_1h": zigzag_kline}))
    svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        engine_config={"runner": "python"},
    )
    assert calls["n"] == 0


class _StubProvider:
    """最小 provider：返回 {key: DataFrame} 形式的 K 线，供 run_backtest 分支测试。"""

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        self._data = data

    def load_multiple(self, **_kwargs):
        return {k: v.copy() for k, v in self._data.items()}, None

    def load_funding_rate(self, symbol, start=None, end=None):
        return None


def _assert_deep_parity(py, rs, path: str = "") -> None:
    """递归比对两条路径的格式化结果（跳过 klines / _meta），数值容差 1e-6。"""
    if isinstance(py, dict) and isinstance(rs, dict):
        for k in set(py) | set(rs):
            if k in ("klines", "_meta"):
                continue
            assert k in py and k in rs, f"{path}.{k} 单边存在"
            _assert_deep_parity(py[k], rs[k], f"{path}.{k}")
    elif isinstance(py, list) and isinstance(rs, list):
        assert len(py) == len(rs), f"{path} 长度不一致"
        for i, (a, b) in enumerate(zip(py, rs, strict=False)):
            _assert_deep_parity(a, b, f"{path}[{i}]")
    elif isinstance(py, bool) or isinstance(rs, bool):
        assert py == rs, f"{path}: {py} vs {rs}"
    elif isinstance(py, (int, float)) and isinstance(rs, (int, float)):
        assert abs(float(py) - float(rs)) <= 1e-6, f"{path}: {py} vs {rs}"
    else:
        assert py == rs, f"{path}: {py!r} vs {rs!r}"


def test_multi_symbol_parity(zigzag_kline: pd.DataFrame) -> None:
    """多品种（每品种独立 runner）鲁棒：两条路径格式化结果完全一致。"""
    data = {"BTCUSDT_1h": zigzag_kline, "ETHUSDT_1h": zigzag_kline.assign(close=zigzag_kline["close"] + 5.0)}
    symbols = ["BTCUSDT", "ETHUSDT"]

    def run(mode: str):
        svc = EventDrivenBacktestService(data_provider=_StubProvider(data))
        return svc.run_backtest(
            strategy_name="dual_ma",
            strategy_params={},
            symbols=symbols,
            timeframes=["1h"],
            engine_config={"runner": mode},
        )

    _assert_deep_parity(run("python"), run("rust"))


def test_force_liquidate_parity(zigzag_kline: pd.DataFrame) -> None:
    """force_liquidate：两条路径一致，且开关确实生效（与不开启相比末态持仓被平）。"""
    svc = EventDrivenBacktestService(data_provider=None)

    py_fl = BacktestLoop(initial_cash=100_000.0).run(
        _BuyThenHold(), zigzag_kline, symbol="BTCUSDT", force_liquidate=True
    )
    rs_fl = svc._run_rust_single(_BuyThenHold(), zigzag_kline, "BTCUSDT", 100_000.0, force_liquidate=True)
    _assert_parity(py_fl, rs_fl)

    # 开关生效证据：与 force=False 相比，末态持仓被 EOD 市价平掉（受 seed 流动性上限，部分平仓）
    py_no = BacktestLoop(initial_cash=100_000.0).run(_BuyThenHold(), zigzag_kline, symbol="BTCUSDT")
    rs_no = svc._run_rust_single(_BuyThenHold(), zigzag_kline, "BTCUSDT", 100_000.0)
    assert py_fl.final_positions != py_no.final_positions
    assert rs_fl.final_positions != rs_no.final_positions


def _spy_rust_calls(monkeypatch) -> dict:
    """包装 _run_rust_single，记录被调用次数。"""
    calls = {"n": 0}
    orig = EventDrivenBacktestService._run_rust_single

    def spy(self, *args, **kwargs):
        calls["n"] += 1
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(EventDrivenBacktestService, "_run_rust_single", spy)
    return calls
