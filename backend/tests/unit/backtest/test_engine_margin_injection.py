"""engine_service 保证金注入（币本位门禁 / 全品种参与 / 预算互斥）与结果透传单测。"""

import pandas as pd
import pytest

from backtest.backtest_loop import BacktestResult
from backtest.engine_service import EventDrivenBacktestService


class _StubProvider:
    """最小 provider：只提供 K 线，资金费固定为空。"""

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        self._data = data

    def load_multiple(self, **_kwargs):
        return {k: v.copy() for k, v in self._data.items()}, None

    def load_funding_rate(self, symbol, start=None, end=None):
        return None

    def load_multiple_data(self, **_kwargs):
        return {}, None


def _kline(n: int = 40) -> pd.DataFrame:
    closes = [100.0 + (i % 10) for i in range(n)]
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=index,
    )


def _service() -> EventDrivenBacktestService:
    data = {"BTCUSDT_1h": _kline(), "ETHUSDT_1h": _kline()}
    return EventDrivenBacktestService(data_provider=_StubProvider(data))


def _run(svc: EventDrivenBacktestService, engine_config: dict, market: str = "um") -> dict:
    return svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframes=["1h"],
        engine_config={"trading_mode": "futures", **engine_config},
        market=market,
    )


def test_coin_margin_rejects_margin_settings():
    """币本位乘数未入账，启用保证金必须直接拒绝而不是给出错误结果"""
    svc = EventDrivenBacktestService(data_provider=None)
    with pytest.raises(ValueError, match="币本位"):
        svc.run_backtest(
            strategy_name="dual_ma",
            strategy_params={},
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            engine_config={
                "trading_mode": "futures",
                "margin_settings": [{"symbol": "BTCUSDT", "leverage": 5, "margin_mode": "cross"}],
            },
            market="cm",
        )


def test_unlisted_symbols_get_default_spec(monkeypatch):
    """启用保证金后未配置的品种按 1x / cross 默认参与（半启用会让全仓 MMR 求和失真）"""
    captured: dict[str, dict] = {}

    def _fake_single(self, strategy, df, symbol, init_cash, **kwargs):
        captured[symbol] = kwargs["margin_specs"]
        return BacktestResult(final_nav=init_cash)

    monkeypatch.setattr(EventDrivenBacktestService, "_run_rust_single", _fake_single)

    _run(
        _service(),
        {"margin_settings": [{"symbol": "BTCUSDT", "leverage": 10, "margin_mode": "cross"}]},
    )

    assert captured["BTCUSDT"]["BTC/USDT"]["leverage"] == 10.0
    eth_spec = captured["ETHUSDT"]["ETH/USDT"]
    assert eth_spec["leverage"] == 1.0
    assert eth_spec["mode"] == "cross"


def test_shared_budget_disabled_when_margin_enabled(monkeypatch):
    """保证金启用时不能再传 shared 敞口预算，否则杠杆放大后的目标会被等比砍回"""
    captured: dict = {}

    def _fake_multi(self, **kwargs):
        captured.update(kwargs)
        entries = kwargs["entries"]
        init_cash = kwargs["init_cash"]
        agg = {"equity_curve": [], "initial_capital": init_cash, "final_nav": init_cash}
        return agg, {sym: [] for sym in entries}, dict.fromkeys(entries, 0)

    monkeypatch.setattr(EventDrivenBacktestService, "_run_rust_multi", _fake_multi)

    _run(
        _service(),
        {
            "capital_mode": "shared",
            "leverage": 10,
            "margin_settings": [{"symbol": "BTCUSDT", "leverage": 20, "margin_mode": "isolated"}],
        },
    )

    assert captured["capital_budget"] is None
    assert captured["margin_specs"]["BTC/USDT"]["mode"] == "isolated"
    assert captured["margin_specs"]["ETH/USDT"]["leverage"] == 1.0


def test_capital_budget_kept_when_margin_disabled(monkeypatch):
    """未启用保证金时 shared 预算保持原口径（防止上面的改动把预算永久关掉）"""
    captured: dict = {}

    def _fake_multi(self, **kwargs):
        captured.update(kwargs)
        entries = kwargs["entries"]
        init_cash = kwargs["init_cash"]
        agg = {"equity_curve": [], "initial_capital": init_cash, "final_nav": init_cash}
        return agg, {sym: [] for sym in entries}, dict.fromkeys(entries, 0)

    monkeypatch.setattr(EventDrivenBacktestService, "_run_rust_multi", _fake_multi)

    _run(_service(), {"capital_mode": "shared", "initial_cash": 10000.0, "leverage": 3})

    assert captured["capital_budget"] == 30000.0
    assert captured["margin_specs"] == {}


def test_map_rust_result_passes_margin_fields():
    """Rust 结果对象 → BacktestResult 时透传强平事件与保证金口径字段"""

    class _FakeRustResult:
        total_pnl = 0.0
        orders_accepted = 0
        orders_rejected = 0
        fills = 0
        final_nav = 10_000.0
        max_drawdown_pct = 0.0
        nav_peak = 10_000.0
        bar_nav_curve = []
        bar_balance_curve = []
        trades = []
        fills_detail = []
        events_processed = 0
        duration_secs = 0.0
        total_fees = 0.0
        win_rate = 0.0
        sharpe_ratio = 0.0
        final_positions = {}
        liquidation_events = [
            {
                "timestamp_ns": 1,
                "symbol": "BTC/USDT",
                "margin_mode": "cross",
                "tier_from": 0,
                "tier_to": 0,
                "reduced_qty": 0.5,
                "price": 100.0,
                "fee": 0.05,
                "reason": "partial",
                "price_basis": "close",
            }
        ]
        insurance_fund_loss = 12.5
        price_basis = "close"
        margin_applied = True
        margin_specs_effective = [
            {"symbol": "BTC/USDT", "leverage": 20.0, "margin_mode": "cross", "bracket_source": "default"}
        ]
        liquidation_count = 1
        margin_shortfall_count = 2

    mapped = EventDrivenBacktestService._map_rust_result(_FakeRustResult(), None, "BTCUSDT")

    assert mapped.liquidation_events[0]["symbol"] == "BTC/USDT"
    assert mapped.insurance_fund_loss == 12.5
    assert mapped.price_basis == "close"
    assert mapped.margin_applied is True
    assert mapped.margin_specs_effective == [
        {"symbol": "BTC/USDT", "leverage": 20.0, "margin_mode": "cross", "bracket_source": "default"}
    ]
    assert mapped.liquidation_count == 1
    assert mapped.margin_shortfall_count == 2


def test_map_rust_result_defaults_when_margin_fields_absent():
    """旧 wheel 结果没有生效回显字段：按 False / [] / 0 / 0 兜底，不抛异常"""

    class _LegacyRustResult:
        total_pnl = 0.0
        orders_accepted = 0
        orders_rejected = 0
        fills = 0
        final_nav = 10_000.0
        max_drawdown_pct = 0.0
        nav_peak = 10_000.0
        bar_nav_curve = []
        trades = []
        fills_detail = []
        events_processed = 0
        duration_secs = 0.0
        total_fees = 0.0
        win_rate = 0.0
        sharpe_ratio = 0.0
        final_positions = {}

    mapped = EventDrivenBacktestService._map_rust_result(_LegacyRustResult(), None, "BTCUSDT")

    assert mapped.margin_applied is False
    assert mapped.margin_specs_effective == []
    assert mapped.liquidation_count == 0
    assert mapped.margin_shortfall_count == 0
