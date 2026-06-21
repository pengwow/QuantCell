# -*- coding: utf-8 -*-
"""AxonBacktestEngine 测试"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


@pytest.fixture
def mock_axon_engine():
    """创建 mock 的 axon BacktestEngine"""
    mock_engine = MagicMock()
    mock_result = SimpleNamespace(
        final_nav=100000.0,
        total_pnl=0.0,
        max_drawdown=0.0,
        orders_accepted=0,
        orders_rejected=0,
        fills=0,
    )
    mock_engine.run.return_value = mock_result
    return mock_engine


@pytest.fixture
def engine_with_mock(mock_axon_engine):
    """创建使用 mock 的 AxonBacktestEngine"""
    with patch("backtest.engines.axon_engine.AXON_AVAILABLE", True):
        with patch("backtest.engines.axon_engine._AxonBacktestEngine", return_value=mock_axon_engine):
            from backtest.engines.axon_engine import AxonBacktestEngine
            engine = AxonBacktestEngine({"initial_capital": 100000.0})
            engine.initialize()
            yield engine, mock_axon_engine


class TestAxonBacktestEngine:
    def test_creation_with_config(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        assert engine._config["initial_capital"] == 100000.0
        assert engine._engine is None

    def test_initialize(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        assert engine._engine is mock_axon
        assert engine._is_initialized is True

    def test_initialize_without_axon_raises(self):
        with patch("backtest.engines.axon_engine.AXON_AVAILABLE", False):
            from backtest.engines.axon_engine import AxonBacktestEngine
            engine = AxonBacktestEngine({"initial_capital": 100000.0})
            with pytest.raises(ImportError, match="axon_quant 未安装"):
                engine.initialize()

    def test_add_data(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        df = pd.DataFrame({
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [103.0, 104.0],
            "volume": [1000.0, 2000.0],
        }, index=pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True))
        engine.add_data(df, "BTCUSDT")
        assert mock_axon.push_event.call_count == 2
        assert len(engine._events) == 2

    def test_add_data_accumulates(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        df1 = pd.DataFrame({
            "open": [100.0], "high": [105.0], "low": [99.0],
            "close": [103.0], "volume": [1000.0],
        }, index=pd.to_datetime(["2026-01-01"], utc=True))
        df2 = pd.DataFrame({
            "open": [101.0], "high": [106.0], "low": [100.0],
            "close": [104.0], "volume": [2000.0],
        }, index=pd.to_datetime(["2026-01-02"], utc=True))
        engine.add_data(df1, "BTCUSDT")
        engine.add_data(df2, "BTCUSDT")
        assert mock_axon.push_event.call_count == 2
        assert len(engine._events) == 2

    def test_submit_order(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        order = {"id": 1, "symbol": "BTCUSDT", "side": "Buy", "type": "limit",
                 "price": 50000.0, "quantity": 0.1, "tif": "GTC"}
        engine.submit_order(order, 1000000000)
        assert mock_axon.push_event.call_count == 1
        call_args = mock_axon.push_event.call_args[0][0]
        assert call_args["type"] == "order_submitted"
        assert call_args["order"]["side"] == "Buy"

    def test_run_returns_result(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        result = engine.run()
        assert "final_nav" in result
        assert "total_pnl" in result
        assert "max_drawdown" in result
        assert result["final_nav"] == 100000.0

    def test_run_idempotent(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        result1 = engine.run()
        result2 = engine.run()
        assert result1["final_nav"] == result2["final_nav"]
        assert mock_axon.run.call_count == 2

    def test_cleanup(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        engine.cleanup()
        assert engine._engine is None
        assert engine._is_initialized is False

    def test_run_without_init_raises(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.run()


class TestAxonBacktestEngineIntegration:
    def test_full_backtest_flow(self, engine_with_mock):
        engine, mock_axon = engine_with_mock
        df = pd.DataFrame({
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [103.0, 104.0, 105.0],
            "volume": [1000.0, 2000.0, 3000.0],
        }, index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"], utc=True))
        engine.add_data(df, "BTCUSDT")
        order = {"id": 1, "symbol": "BTCUSDT", "side": "Buy", "type": "limit",
                 "price": 100.0, "quantity": 1.0, "tif": "GTC"}
        engine.submit_order(order, 1735689600000000000)
        result = engine.run()
        assert result["final_nav"] == 100000.0
        engine.cleanup()
