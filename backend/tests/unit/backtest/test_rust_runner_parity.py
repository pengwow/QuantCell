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

from backtest.backtest_loop import BacktestLoop, clean_ohlcv_df
from backtest.data_adapters.base_adapter import AdapterResult
from backtest.engine_service import (
    RUST_RUNNER_DATA_TYPES,
    EventDrivenBacktestService,
    adapter_feature_frame,
)
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


def test_run_rust_single_uses_requested_symbol(zigzag_kline: pd.DataFrame) -> None:
    """多品种「独立资金池」分支复用同一策略实例时，引擎 instrument 必须取**入参** symbol。

    回归守卫：统一 run 入口后，引擎按 `strategy.symbol()` 建 instrument，而 else 分支
    复用的策略实例其 config.symbol 固定为首品种。若适配器不显式覆盖 symbol，入参品种的
    数据会被跑到首品种的 instrument 上——旧 API 传扁平 `bars` 时查不出来，因为
    `final_positions` 从不进入导出载荷。
    """
    svc = EventDrivenBacktestService(data_provider=None)
    # _BuyThenHold 的 config.symbol 固定为 BTCUSDT，正模拟 else 分支复用的首品种策略实例
    assert _BuyThenHold().config.symbol == "BTCUSDT"

    res = svc._run_rust_single(_BuyThenHold(), zigzag_kline, "ETHUSDT", 100_000.0)

    assert res.final_positions, "应有持仓（未开启 force_liquidate）"
    # final_positions 的键是 instrument 元组，spot 形如 ("spot", base, quote)
    assert all(k[1] == "ETH" and k[2] == "USDT" for k in res.final_positions), (
        f"instrument 应取入参 symbol ETH/USDT，实际 {list(res.final_positions)}"
    )


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


# ──────────────────────────────────────────────────────────────────────
# 非 K 线 data_type 放行（含适配器 feature_* 列接入特征通道）
# ──────────────────────────────────────────────────────────────────────

# 各适配器实际会产出的 feature_* 列（kline 家族 / tick 家族不产特征列）
_FEATURE_COLS_BY_TYPE = {
    "bookDepth": ["feature_mid_price"],
    "bookTicker": ["feature_mid_price", "feature_spread"],
    "fundingRate": ["feature_funding_rate"],
    "openInterest": ["feature_open_interest", "feature_open_interest_value"],
}

_NON_KLINE_TYPES = sorted(RUST_RUNNER_DATA_TYPES - {"kline"})


def _adapter_frame(df: pd.DataFrame, data_type: str) -> pd.DataFrame:
    """复刻适配器输出契约：大写 OHLCV + int64 纳秒 timestamp 列 + feature_* 列 + RangeIndex。"""
    frame = pd.DataFrame(
        {
            "Open": df["open"].values,
            "High": df["high"].values,
            "Low": df["low"].values,
            "Close": df["close"].values,
            "Volume": df["volume"].values,
        }
    )
    for col in _FEATURE_COLS_BY_TYPE.get(data_type, []):
        # 用 close 派生一个确定性特征序列（非 NaN，索引对齐 bar）
        frame[col] = df["close"].values if col == "feature_mid_price" else [float(i) for i in range(len(df))]
    frame["timestamp"] = [int(pd.Timestamp(i).timestamp() * 1_000_000_000) for i in df.index]
    return frame


class _StubAdapterProvider:
    """最小 provider：非 K 线走 `load_multiple_data` 适配器入口，直接返回给定 AdapterResult。"""

    def __init__(self, results: dict[str, AdapterResult]) -> None:
        self._results = results

    def load_multiple_data(self, **_kwargs):
        return dict(self._results), None

    def load_funding_rate(self, symbol, start=None, end=None):
        return None


def test_adapter_frame_contract_roundtrip(zigzag_kline: pd.DataFrame) -> None:
    """适配器帧能被 Rust 路径入口无损消费：列归一 + 纳秒时间戳逐位保留。"""
    frame = _adapter_frame(zigzag_kline, "bookTicker")
    expected_ns = [int(pd.Timestamp(i).timestamp() * 1_000_000_000) for i in zigzag_kline.index]

    bars = EventDrivenBacktestService._df_to_rust_bars(clean_ohlcv_df(frame))

    assert len(bars) == len(zigzag_kline)
    assert [b["timestamp"] for b in bars] == expected_ns
    assert bars[0]["close"] == pytest.approx(float(zigzag_kline["close"].iloc[0]))
    assert bars[0]["volume"] == pytest.approx(float(zigzag_kline["volume"].iloc[0]))


def test_adapter_feature_frame_strips_prefix_and_aligns(zigzag_kline: pd.DataFrame) -> None:
    """批2：feature_* 列 → 去掉前缀的特征帧，索引对齐 bar 时间戳。"""
    feat = adapter_feature_frame(_adapter_frame(zigzag_kline, "bookTicker"))

    assert feat is not None
    assert list(feat.columns) == ["mid_price", "spread"]
    assert isinstance(feat.index, pd.DatetimeIndex)
    # 对齐口径看纳秒值本身（索引是 tz-aware，bar 索引 naive，直接比较 Timestamp 会因 tz 不等）
    assert int(feat.index[0].value) == int(zigzag_kline.index[0].value)


def test_adapter_feature_frame_none_without_feature_cols(zigzag_kline: pd.DataFrame) -> None:
    """无 feature_* 列（kline / tick 家族）→ 不注入特征。"""
    assert adapter_feature_frame(_adapter_frame(zigzag_kline, "aggTrades")) is None


def test_adapter_feature_frame_none_without_time_source() -> None:
    """有 feature_* 列但拿不到时间来源 → 返回 None，避免特征错位到别的 bar。"""
    assert adapter_feature_frame(pd.DataFrame({"feature_x": [1.0, 2.0]})) is None


@pytest.mark.parametrize("data_type", _NON_KLINE_TYPES)
def test_non_kline_parity(data_type: str, zigzag_kline: pd.DataFrame) -> None:
    """9 类非 K 线 data_type 放行后，两条编排路径的格式化结果完全一致。"""
    result = AdapterResult(data=_adapter_frame(zigzag_kline, data_type), metadata={"data_type": data_type})

    def run(mode: str):
        svc = EventDrivenBacktestService(data_provider=_StubAdapterProvider({"BTCUSDT_1h": result}))
        return svc.run_backtest(
            strategy_name="dual_ma",
            strategy_params={},
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            data_type=data_type,
            market="um",
            engine_config={"runner": mode},
        )

    _assert_deep_parity(run("python"), run("rust"))


@pytest.mark.parametrize("data_type", _NON_KLINE_TYPES)
def test_non_kline_uses_rust_by_default(data_type: str, zigzag_kline: pd.DataFrame, monkeypatch) -> None:
    """非 K 线默认也走 Rust 路径（gate 是白名单，不是 == \"kline\"）。"""
    calls = _spy_rust_calls(monkeypatch)
    result = AdapterResult(data=_adapter_frame(zigzag_kline, data_type), metadata={"data_type": data_type})
    svc = EventDrivenBacktestService(data_provider=_StubAdapterProvider({"BTCUSDT_1h": result}))
    svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        data_type=data_type,
        market="um",
        engine_config={},
    )
    assert calls["n"] == 1


def test_unknown_data_type_still_falls_back_to_python(zigzag_kline: pd.DataFrame, monkeypatch) -> None:
    """不在放行集合内的 data_type 必须回退 Python 路径（gate 不得静默全放行）。"""
    calls = _spy_rust_calls(monkeypatch)
    result = AdapterResult(data=_adapter_frame(zigzag_kline, "bookTicker"), metadata={"data_type": "someNewType"})
    svc = EventDrivenBacktestService(data_provider=_StubAdapterProvider({"BTCUSDT_1h": result}))
    svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        data_type="someNewType",
        market="um",
        engine_config={},
    )
    assert calls["n"] == 0


def test_adapter_feature_injection_parity(zigzag_kline: pd.DataFrame) -> None:
    """批2 行为验证：策略真的读到了适配器派生的特征（mid_price），两条路径一致。"""
    feat = adapter_feature_frame(_adapter_frame(zigzag_kline, "bookTicker"))

    py_res = BacktestLoop(initial_cash=100_000.0).run(
        _FactorTiming("mid_price"), zigzag_kline, symbol="BTCUSDT", feature_dataframe=feat
    )
    rust_res = EventDrivenBacktestService(data_provider=None)._run_rust_single(
        _FactorTiming("mid_price"), zigzag_kline, "BTCUSDT", 100_000.0, feature_dataframe=feat
    )

    _assert_parity(py_res, rust_res)
    # 特征缺失时该策略全程 hold（0 成交），有成交即证明两条路径都真的消费到了特征
    assert py_res.fills > 0
    assert rust_res.fills > 0


# ──────────────────────────────────────────────────────────────────────
# 永续保证金结算方式（market → settle）
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("settle", ["usd_margin", "coin_margin"])
def test_swap_settle_tag_parity(settle: str, zigzag_kline: pd.DataFrame) -> None:
    """settle 如实落到品种元组，两条路径一致（币本位不再被写成 usd_margin）。"""
    py_res = BacktestLoop(initial_cash=100_000.0).run(
        _BuyThenHold(), zigzag_kline, symbol="BTCUSDT", trading_mode="futures", settle=settle
    )
    rust_res = EventDrivenBacktestService(data_provider=None)._run_rust_single(
        _BuyThenHold(), zigzag_kline, "BTCUSDT", 100_000.0, futures=True, settle=settle
    )

    _assert_parity(py_res, rust_res)
    assert py_res.final_positions, "末态应有持仓，否则 settle 断言无意义"
    assert all(settle in str(k) for k in py_res.final_positions)


@pytest.mark.parametrize("market,expected_settle", [("um", "usd_margin"), ("cm", "coin_margin")])
def test_market_drives_settle(market: str, expected_settle: str, zigzag_kline: pd.DataFrame, monkeypatch) -> None:
    """run_backtest 里 market → settle 的推导：cm 走 coin_margin，um 走 usd_margin。"""
    captured: dict = {}
    orig = EventDrivenBacktestService._run_rust_single

    def spy(self, *args, **kwargs):
        captured.update(kwargs)
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(EventDrivenBacktestService, "_run_rust_single", spy)
    svc = EventDrivenBacktestService(data_provider=_StubProvider({"BTCUSDT_1h": zigzag_kline}))
    svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        market=market,
        engine_config={"trading_mode": "futures"},
    )

    assert captured["futures"] is True
    assert captured["settle"] == expected_settle


def test_unknown_settle_rejected(zigzag_kline: pd.DataFrame) -> None:
    """信任边界：未知 settle 两条路径都必须拒绝，不得静默按默认值跑。"""
    with pytest.raises(ValueError):
        BacktestLoop(initial_cash=100_000.0).run(
            _BuyThenHold(), zigzag_kline, symbol="BTCUSDT", trading_mode="futures", settle="bogus"
        )

    svc = EventDrivenBacktestService(data_provider=None)
    with pytest.raises(ValueError):
        svc._run_rust_single(_BuyThenHold(), zigzag_kline, "BTCUSDT", 100_000.0, futures=True, settle="bogus")
