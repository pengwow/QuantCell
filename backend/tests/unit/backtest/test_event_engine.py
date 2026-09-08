"""backtest.engines.event_engine 单元测试。

覆盖：
- _safe_float / _instrument_id_from_dict（模块级/静态方法）
- _normalize_trades / _normalize_positions / _normalize_equity_curve / _build_account_info / _build_metrics
- initialize（函数内 import axon_bridge，monkeypatch）
- add_funding_data（时间戳转换与排序，monkeypatch axon_bridge.to_ns_timestamp）
- submit_order（普通订单走 build_order_submitted_event，取消订单原样透传）
- load_data_from_csv / load_data_from_parquet（tmp_path 真实文件）
- run_backtest（FakeEngine 驱动 begin_bar / step / push_funding / run）
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from backtest.engines.base import EngineType
from backtest.engines.event_engine import (
    EventDrivenBacktestEngine,
    _safe_float,
)

NS_TS = 1_704_067_200_000_000_000  # 2024-01-01 00:00:00 UTC（纳秒）
SEC_TS = 1_704_067_200  # 同一时刻（秒）

INSTRUMENT = {"base": "BTC", "quote": "USDT"}


# =================== 测试辅助 ===================


class FakeEngine:
    """按 EventDrivenBacktestEngine 使用方式实现的假引擎。"""

    def __init__(self):
        self.begin_bars: list[tuple] = []
        self.events: list[dict] = []
        self.funding_events: list[dict] = []
        self.step_calls = 0
        self.run_calls = 0
        self._finished = False

    @property
    def is_finished(self) -> bool:
        return self._finished

    def begin_bar(self, price, instrument):
        self.begin_bars.append((price, instrument))

    def step(self):
        self.step_calls += 1
        return SimpleNamespace(fills=2, events_processed=3)

    def push_event(self, event):
        self.events.append(event)

    def push_funding(self, **kwargs):
        self.funding_events.append(kwargs)

    def run(self):
        self.run_calls += 1
        self._finished = True
        return SimpleNamespace(done=True)


class FakeStrategy:
    """记录 on_start / on_bar / on_stop 调用。"""

    def __init__(self):
        self.bars: list[dict] = []
        self.started = False
        self.stopped = False

    def on_start(self):
        self.started = True

    def on_bar(self, bar: dict):
        self.bars.append(bar)

    def on_stop(self):
        self.stopped = True


def _instrument_id(instrument: dict) -> str:
    return f"{instrument['base']}{instrument['quote']}"


def _write_ohlcv_csv(tmp_path, rows: list[tuple], sep: str = ";") -> str:
    """写入一行一个 K 线的 CSV 文件，返回路径。"""
    path = tmp_path / "bars.csv"
    lines = [sep.join(["timestamp", "open", "high", "low", "close", "volume"])]
    for r in rows:
        lines.append(sep.join(str(x) for x in r))
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


CSV_ROWS = [
    ("2024-01-01 00:00:00", 100.0, 105.0, 99.0, 102.0, 1000.0),
    ("2024-01-01 00:01:00", 102.0, 107.0, 101.0, 106.0, 1200.0),
    ("2024-01-01 00:02:00", 106.0, 109.0, 104.0, 108.0, 900.0),
]


def _make_engine(monkeypatch) -> tuple[EventDrivenBacktestEngine, FakeEngine]:
    """构造已完成 initialize 的引擎（monkeypatch create_backtest_engine 返回 FakeEngine）。

    时间戳转换固定为 ts.value（纳秒），避免受运行机器时区影响。
    """
    engine = EventDrivenBacktestEngine(
        {"initial_capital": 100000.0, "start_date": "2024-01-01", "end_date": "2024-01-02"}
    )
    fake = FakeEngine()
    monkeypatch.setattr("axon_bridge.create_backtest_engine", lambda config: fake)
    monkeypatch.setattr("axon_bridge.to_ns_timestamp", lambda ts: int(ts.value))
    engine.initialize()
    return engine, fake


# ==================== 纯函数: _safe_float ====================


def test_safe_float_valid_values():
    assert _safe_float("12.5") == 12.5
    assert _safe_float(3) == 3.0
    assert _safe_float(True) == 1.0


def test_safe_float_none_and_invalid_returns_default():
    assert _safe_float(None) == 0.0
    assert _safe_float("abc") == 0.0
    assert _safe_float([1, 2]) == 0.0
    assert _safe_float(None, default=7.5) == 7.5


# ==================== normalize 系列 ====================


def test_normalize_trades_full_mapping_with_ns_timestamp():
    raw = [
        {
            "ts": NS_TS,
            "price": 100.5,
            "quantity": 2.0,
            "side": "BUY",
            "status": "filled",
            "trade_id": "t-1",
            "order_id": "o-1",
            "symbol": "BTCUSDT",
            "commission": "0.05",
        }
    ]
    trades = EventDrivenBacktestEngine()._normalize_trades(raw)
    assert len(trades) == 1
    t = trades[0]
    assert t["trade_id"] == "t-1"
    assert t["client_order_id"] == "o-1"
    assert t["symbol"] == "BTCUSDT"
    assert t["side"] == "BUY"
    assert t["direction"] == "买入"
    assert t["quantity"] == 2.0
    assert t["price"] == 100.5
    assert t["volume"] == 201.0
    assert t["commission"] == "0.05"
    assert t["status"] == "filled"
    assert t["timestamp"] == SEC_TS
    assert t["formatted_time"] == "2024-01-01 00:00:00"


def test_normalize_trades_ms_and_sec_timestamp():
    engine = EventDrivenBacktestEngine()
    for ts in [1_704_067_200_000, SEC_TS]:
        trades = engine._normalize_trades([{"ts": ts, "side": "sell"}])
        assert trades[0]["timestamp"] == SEC_TS
        assert trades[0]["formatted_time"] == "2024-01-01 00:00:00"


def test_normalize_trades_zero_ts_and_fallback_fields():
    trades = EventDrivenBacktestEngine()._normalize_trades(
        [
            {
                "timestamp": 0,
                "avg_px": 10.0,
                "qty": 3.0,
                "side": "1",
                "commission": "0.1",
            }
        ]
    )
    t = trades[0]
    assert t["timestamp"] == 0
    assert t["formatted_time"] == ""
    assert t["price"] == 10.0
    assert t["quantity"] == 3.0
    assert t["direction"] == "卖出"


def test_normalize_trades_ignores_non_dict():
    assert EventDrivenBacktestEngine()._normalize_trades(["str", 123, None]) == []


def test_normalize_positions_defaults_and_fallbacks():
    positions = EventDrivenBacktestEngine()._normalize_positions(
        [
            {"qty": -2.0, "avg_px": 90.0, "side": "long"},
            {"id": "p-2", "symbol": "BTCUSDT", "quantity": 1.5, "avg_price": 88.0, "realized_pnl": 3.2},
        ]
    )
    p0 = positions[0]
    assert p0["position_id"] == "POS_0"
    assert p0["quantity"] == -2.0
    assert p0["trade_quantity"] == 2.0
    assert p0["signed_quantity"] == -2.0
    assert p0["side"] == "long"
    p1 = positions[1]
    assert p1["position_id"] == "p-2"
    assert p1["symbol"] == "BTCUSDT"
    assert p1["quantity"] == 1.5
    assert p1["avg_px_open"] == 88.0
    assert p1["realized_pnl"] == "3.2"


def test_normalize_equity_curve_dict_int_and_skip():
    curve = EventDrivenBacktestEngine()._normalize_equity_curve(
        [{"nav": 100.0, "equity": 99.0}, 200, "oops", {"equity": 300.0}]
    )
    assert len(curve) == 3
    assert curve[0]["equity"] == curve[0]["balance"] == 100.0
    assert curve[1]["timestamp"] == 1
    assert curve[1]["equity"] == 200.0
    # timestamp 取 enumerate 下标，被跳过的 "oops" 仍占序号 → 末元素为 3
    assert curve[2]["timestamp"] == 3
    assert curve[2]["equity"] == 300.0


def test_normalize_equity_curve_empty():
    assert EventDrivenBacktestEngine()._normalize_equity_curve([]) == []


# ==================== _build_account_info / _build_metrics ====================


def test_build_account_info_mapping():
    info = EventDrivenBacktestEngine()._build_account_info({"final_nav": 123.0, "nav_peak": 130.0, "total_fees": 4.0})
    assert info["balance"] == 123.0
    assert info["equity"] == 123.0
    assert info["final_balance"] == 123.0
    assert info["initial_balance"] == 130.0
    assert info["max_balance"] == 130.0
    assert info["peak_equity"] == 130.0
    assert info["total_commissions"] == 4.0


def test_build_account_info_missing_keys_zeros():
    info = EventDrivenBacktestEngine()._build_account_info({})
    assert info["balance"] == 0.0
    assert info["total_commissions"] == 0.0


def test_build_metrics_win_rate_times_100_and_trades_len():
    raw = {
        "total_pnl": 1000.0,
        "total_fees": 5.0,
        "sharpe_ratio": 1.23456,
        "max_drawdown_pct": 2.5,
        "win_rate": 0.5,
        "trades": [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}],
        "final_nav": 110000.0,
        "initial_cash": 100000.0,
    }
    m = EventDrivenBacktestEngine()._build_metrics(raw)
    assert m["win_rate"] == 50.0
    assert m["total_trades"] == 4
    assert m["winning_trades"] == 2
    assert m["losing_trades"] == 2
    assert m["total_return"] == 10.0
    assert m["sharpe_ratio"] == 1.2346
    assert m["max_drawdown"] == 2.5
    assert m["total_pnl"] == 1000.0


def test_build_metrics_win_rate_1_0_becomes_100():
    m = EventDrivenBacktestEngine()._build_metrics({"win_rate": 1.0, "trades": [1, 2]})
    assert m["win_rate"] == 100.0
    assert m["winning_trades"] == 2


def test_build_metrics_pct_win_rate_not_converted_again():
    # 原始值已是百分比（>1）则不重复乘 100
    m = EventDrivenBacktestEngine()._build_metrics({"win_rate": 60.0, "trades": [1, 2]})
    assert m["win_rate"] == 60.0


def test_build_metrics_fallback_to_total_trades_and_fills():
    engine = EventDrivenBacktestEngine()
    assert engine._build_metrics({"trades": [], "total_trades": 7})["total_trades"] == 7
    assert engine._build_metrics({"trades": [], "fills": 3})["total_trades"] == 3


def test_build_metrics_initial_cash_falls_back_to_nav_peak():
    m = EventDrivenBacktestEngine()._build_metrics({"final_nav": 110000.0, "nav_peak": 100000.0, "trades": [1]})
    assert m["total_return"] == 10.0


# ==================== _instrument_id_from_dict ====================


def test_instrument_id_from_dict_base_quote():
    assert EventDrivenBacktestEngine()._instrument_id_from_dict({"base": "ETH", "quote": "USDT"}) == "ETHUSDT"


def test_instrument_id_from_dict_without_base_quote_and_non_dict():
    engine = EventDrivenBacktestEngine()
    assert engine._instrument_id_from_dict({"symbol": "BTCUSDT"}) == "{'symbol': 'BTCUSDT'}"
    assert engine._instrument_id_from_dict(123) == "123"


# ==================== initialize ====================


def test_initialize_creates_bridge_engine(monkeypatch):
    captured = {}

    def fake_create(config):
        captured["config"] = config
        return FakeEngine()

    engine = EventDrivenBacktestEngine(
        {
            "initial_capital": 50000.0,
            "start_date": "2024-01-01",
            "end_date": "2024-01-02",
            "half_spread": 0.005,
        }
    )
    monkeypatch.setattr("axon_bridge.create_backtest_engine", fake_create)
    engine.initialize()

    assert engine.engine_type == EngineType.EVENT_DRIVEN
    assert engine.is_initialized
    assert isinstance(engine._engine, FakeEngine)
    assert captured["config"].initial_cash == 50000.0
    assert captured["config"].half_spread == 0.005
    assert captured["config"].depth_levels == 5


def test_initialize_invalid_config_raises_runtime_error():
    engine = EventDrivenBacktestEngine()
    with pytest.raises(RuntimeError, match="配置验证失败"):
        engine.initialize()


def test_initialize_bridge_failure_wraps_runtime_error(monkeypatch):
    def boom(_config):
        raise RuntimeError("boom")

    engine = EventDrivenBacktestEngine(
        {"initial_capital": 100000.0, "start_date": "2024-01-01", "end_date": "2024-01-02"}
    )
    monkeypatch.setattr("axon_bridge.create_backtest_engine", boom)
    with pytest.raises(RuntimeError, match="引擎初始化失败: boom"):
        engine.initialize()


# ==================== add_funding_data ====================


def test_add_funding_data_converts_and_sorts(monkeypatch):
    engine = EventDrivenBacktestEngine()
    funding_df = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0002], "mark_price": [100.0, 101.0]},
        index=[pd.Timestamp("2024-01-01 01:00:00"), pd.Timestamp("2024-01-01 00:00:00")],
    )

    def fake_to_ns(ts):
        return int(ts.value)

    monkeypatch.setattr("axon_bridge.to_ns_timestamp", fake_to_ns)

    engine.add_funding_data(INSTRUMENT, funding_df)

    events = engine._funding_events["BTCUSDT"]
    # 时间经函数内导入的 to_ns_timestamp 转换后按升序排列：00:00 在前
    assert len(events) == 2
    assert events[0][0] < events[1][0]
    assert events[0][1:] == (0.0002, 101.0)
    assert events[1][1:] == (0.0001, 100.0)


def test_add_funding_data_empty_df_is_noop():
    engine = EventDrivenBacktestEngine()
    engine.add_funding_data(INSTRUMENT, pd.DataFrame())
    assert engine._funding_events == {}


def test_add_funding_data_without_mark_price_uses_zero(monkeypatch):
    engine = EventDrivenBacktestEngine()
    df = pd.DataFrame({"funding_rate": [0.0001]}, index=[pd.Timestamp("2024-01-01 00:00:00")])
    monkeypatch.setattr("axon_bridge.to_ns_timestamp", lambda _ts: 0)
    engine.add_funding_data(INSTRUMENT, df)
    assert engine._funding_events["BTCUSDT"] == [(0, 0.0001, 0.0)]


# ==================== submit_order ====================


def test_submit_order_builds_submitted_event(monkeypatch):
    engine = EventDrivenBacktestEngine()
    fake = FakeEngine()
    engine._engine = fake
    order = {"id": "o-1", "symbol": "BTCUSDT", "side": "buy", "quantity": 1.0, "price": 100.0}
    engine.submit_order(order, NS_TS)

    assert len(fake.events) == 1
    ev = fake.events[0]
    assert ev["id"] == "o-1"
    assert ev["type"] == "order_submitted"
    assert ev["timestamp_ns"] == NS_TS
    assert ev["order"] == order


def test_submit_order_cancelled_passes_through():
    engine = EventDrivenBacktestEngine()
    fake = FakeEngine()
    engine._engine = fake
    cancel = {"type": "order_cancelled", "order_id": "o-1"}
    engine.submit_order(cancel, NS_TS)
    assert fake.events == [cancel]


def test_submit_order_without_engine_raises():
    engine = EventDrivenBacktestEngine()
    with pytest.raises(RuntimeError, match="引擎未初始化"):
        engine.submit_order({"id": "o-1"}, 1)


# ==================== load_data_from_csv / parquet ====================


def test_load_data_from_csv_sets_metadata_and_count(tmp_path):
    csv_path = _write_ohlcv_csv(tmp_path, CSV_ROWS)
    engine = EventDrivenBacktestEngine()
    df = engine.load_data_from_csv(csv_path, INSTRUMENT)

    assert isinstance(df.index, pd.DatetimeIndex)
    assert engine.get_data_count() == 3
    assert _instrument_id(INSTRUMENT) in engine._dataframes


def test_load_data_from_csv_missing_file_raises(tmp_path):
    engine = EventDrivenBacktestEngine()
    with pytest.raises(FileNotFoundError, match="CSV 文件不存在"):
        engine.load_data_from_csv(tmp_path / "nope.csv", INSTRUMENT)


def test_load_data_from_csv_missing_column_raises(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("timestamp;open;high;low;volume\n2024-01-01 00:00:00;1;2;0.5;10", encoding="utf-8")
    engine = EventDrivenBacktestEngine()
    with pytest.raises(RuntimeError, match="缺少必需的列: close"):
        engine.load_data_from_csv(str(path), INSTRUMENT)


def test_load_data_from_parquet(tmp_path):
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 00:05:00"]),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [100.0, 200.0],
        }
    )
    path = tmp_path / "bars.parquet"
    df.to_parquet(path, index=False)
    engine = EventDrivenBacktestEngine()
    loaded = engine.load_data_from_parquet(path, INSTRUMENT)
    assert len(loaded) == 2
    assert engine.get_data_count() == 2


# ==================== run_backtest ====================


def test_run_backtest_drives_fake_engine(tmp_path, monkeypatch):
    csv_path = _write_ohlcv_csv(tmp_path, CSV_ROWS)

    monkeypatch.setattr(
        "axon_bridge.extract_run_result",
        lambda _result: {
            "trades": [
                {"ts": NS_TS, "price": 100.0, "quantity": 1.0, "side": "BUY", "symbol": "BTCUSDT"},
                {"ts": NS_TS + 60_000_000_000, "price": 105.0, "quantity": 1.0, "side": "SELL", "symbol": "BTCUSDT"},
            ],
            "positions": [{"position_id": "p1", "symbol": "BTCUSDT", "quantity": 0.0, "realized_pnl": "0"}],
            "equity_curve": [{"nav": 100000.0}, {"nav": 101000.0}],
            "final_nav": 101000.0,
            "nav_peak": 101000.0,
            "total_pnl": 1000.0,
            "total_fees": 1.0,
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 2.0,
            "win_rate": 0.5,
        },
    )

    engine, fake = _make_engine(monkeypatch)
    engine.load_data_from_csv(csv_path, INSTRUMENT)
    strategy = FakeStrategy()
    engine.add_strategy(strategy)

    results = engine.run_backtest()

    assert strategy.started and strategy.stopped
    assert len(strategy.bars) == 3
    assert strategy.bars[0]["instrument_id"] == "BTCUSDT"
    assert strategy.bars[0]["close"] == 102.0
    assert strategy.bars[0]["ts_event"] == NS_TS and strategy.bars[0]["timestamp"] == NS_TS
    assert [price for price, _ in fake.begin_bars] == [102.0, 106.0, 108.0]
    assert fake.step_calls == 3
    assert fake.run_calls >= 1
    assert results["_raw"]["final_nav"] == 101000.0
    assert len(results["trades"]) == 2
    assert results["metrics"]["total_trades"] == 2
    assert results["metrics"]["win_rate"] == 50.0
    assert results["account"]["balance"] == 101000.0
    # step 返回 stats: fills=2 / events_processed=3 × 3 根 bar
    assert engine._total_events == 9
    assert engine._total_fills == 6


def test_run_backtest_pushes_funding_before_bars(tmp_path, monkeypatch):
    csv_path = _write_ohlcv_csv(tmp_path, CSV_ROWS)
    monkeypatch.setattr("axon_bridge.extract_run_result", lambda _r: {})

    engine, fake = _make_engine(monkeypatch)
    engine.load_data_from_csv(csv_path, INSTRUMENT)

    funding_df = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0002]},
        index=[pd.Timestamp("2023-12-31 23:30:00"), pd.Timestamp("2023-12-31 23:45:00")],
    )
    engine.add_funding_data(INSTRUMENT, funding_df)
    strategy = FakeStrategy()
    engine.add_strategy(strategy)

    engine.run_backtest()

    assert len(fake.funding_events) == 2
    # mark_price 缺失时回退到第一个 bar 的收盘价
    assert fake.funding_events[0]["mark_price"] == 102.0
    assert fake.funding_events[0]["funding_rate"] == 0.0001
    assert fake.funding_events[1]["funding_rate"] == 0.0002
    assert [ev["timestamp_ns"] for ev in fake.funding_events] == sorted(
        ev["timestamp_ns"] for ev in fake.funding_events
    )


def test_run_backtest_preconditions():
    engine = EventDrivenBacktestEngine()
    with pytest.raises(RuntimeError, match="引擎未初始化"):
        engine.run_backtest()

    engine._is_initialized = True
    with pytest.raises(RuntimeError, match="未添加策略"):
        engine.run_backtest()

    engine._strategies = [FakeStrategy()]
    with pytest.raises(RuntimeError, match="未加载数据"):
        engine.run_backtest()


def test_run_backtest_with_no_result_data_falls_back(tmp_path, monkeypatch):
    csv_path = _write_ohlcv_csv(tmp_path, CSV_ROWS)
    monkeypatch.setattr("axon_bridge.extract_run_result", lambda _r: {})
    engine, _ = _make_engine(monkeypatch)
    engine.load_data_from_csv(csv_path, INSTRUMENT)
    engine.add_strategy(FakeStrategy())
    results = engine.run_backtest()
    assert results["trades"] == []
    assert results["metrics"]["total_trades"] == 0
