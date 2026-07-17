"""BaselineBacktestService 新参数测试。"""
import pytest
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
