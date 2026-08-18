"""BaselineBacktestService 新参数测试。"""

from backtest.baseline import BaselineBacktestService


def test_baseline_accepts_funding_history_path():
    """构造器接受 funding_history_path 参数。"""
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        funding_history_path="tests/fixtures/funding_history_btcusdt_sample.csv",
    )
    assert svc.funding_history_path == "tests/fixtures/funding_history_btcusdt_sample.csv"


def test_baseline_accepts_spot_symbol():
    """构造器接受 spot_symbol 参数。"""
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT-PERP",
        start="2024-07-01",
        end="2024-07-08",
        spot_symbol="BTCUSDT",
    )
    assert svc.spot_symbol == "BTCUSDT"


def test_baseline_funding_history_path_optional():
    """funding_history_path 默认 None(单 symbol 老用法兼容)。"""
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
    )
    assert svc.funding_history_path is None
    assert svc.spot_symbol is None


def test_baseline_load_funding_history():
    """_load_funding_history() 正确解析 CSV。"""
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        funding_history_path="tests/fixtures/funding_history_btcusdt_sample.csv",
    )
    history = svc._load_funding_history()
    assert isinstance(history, dict)
    assert len(history) > 0
    first_ts = sorted(history.keys())[0]
    assert first_ts > 0
    assert -1 < history[first_ts] < 1  # funding rate 在 (-1, 1)


# ---- funding_injection_window_hours 修复测试 (2026-07-17) ----


def test_baseline_accepts_funding_injection_window_hours():
    """构造器接受 funding_injection_window_hours 参数, 默认 8.0。"""
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
    )
    assert svc.funding_injection_window_hours == 8.0

    svc2 = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        funding_injection_window_hours=4.0,
    )
    assert svc2.funding_injection_window_hours == 4.0


def test_baseline_funding_periods_computed():
    """_compute_funding_periods 把 {ts: rate} 展开为 [(start, end, rate)] list。"""
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        funding_injection_window_hours=8.0,
    )
    history = {1719792000000: 0.0005}  # 2024-07-01 00:00 UTC
    periods = svc._compute_funding_periods(history)
    assert len(periods) == 1
    start_ms, end_ms, rate = periods[0]
    assert end_ms == 1719792000000
    assert start_ms == 1719792000000 - 8 * 3600 * 1000  # 8h before
    assert rate == 0.0005


def test_baseline_funding_periods_empty():
    """空 funding_history → 空 periods。"""
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
    )
    periods = svc._compute_funding_periods({})
    assert periods == []
