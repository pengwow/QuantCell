# -*- coding: utf-8 -*-
"""多品种回测编排器测试"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [99.0, 100.0, 101.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000.0, 2000.0, 3000.0],
    }, index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"], utc=True))


class TestMultiSymbolBacktestRunner:
    def test_creation(self):
        from axond.backtest_runner import MultiSymbolBacktestRunner
        runner = MultiSymbolBacktestRunner({"initial_capital": 100000.0})
        assert runner._config["initial_capital"] == 100000.0
        assert len(runner._engines) == 0

    def test_add_symbol(self, sample_df):
        from axond.backtest_runner import MultiSymbolBacktestRunner
        with patch("axond.backtest_runner.AxonBacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            MockEngine.return_value = mock_instance
            runner = MultiSymbolBacktestRunner({"initial_capital": 100000.0})
            runner.add_symbol("BTCUSDT", sample_df)
            assert "BTCUSDT" in runner._engines
            mock_instance.initialize.assert_called_once()
            mock_instance.add_data.assert_called_once()

    def test_add_multiple_symbols(self, sample_df):
        from axond.backtest_runner import MultiSymbolBacktestRunner
        with patch("axond.backtest_runner.AxonBacktestEngine") as MockEngine:
            MockEngine.return_value = MagicMock()
            runner = MultiSymbolBacktestRunner({"initial_capital": 100000.0})
            runner.add_symbol("BTCUSDT", sample_df)
            runner.add_symbol("ETHUSDT", sample_df)
            assert len(runner._engines) == 2

    def test_run_executes_all_engines(self, sample_df):
        from axond.backtest_runner import MultiSymbolBacktestRunner
        with patch("axond.backtest_runner.AxonBacktestEngine") as MockEngine:
            mock_result = SimpleNamespace(
                final_nav=100000.0, total_pnl=0.0, max_drawdown=0.0,
                orders_accepted=0, orders_rejected=0, fills=0,
            )
            mock_instance = MagicMock()
            mock_instance.run.return_value = {
                "final_nav": 100000.0, "total_pnl": 0.0, "max_drawdown": 0.0,
                "orders_accepted": 0, "orders_rejected": 0, "fills": 0,
            }
            MockEngine.return_value = mock_instance
            runner = MultiSymbolBacktestRunner({"initial_capital": 100000.0})
            runner.add_symbol("BTCUSDT", sample_df)
            runner.add_symbol("ETHUSDT", sample_df)
            results = runner.run()
            assert "BTCUSDT" in results
            assert "ETHUSDT" in results

    def test_get_results(self, sample_df):
        from axond.backtest_runner import MultiSymbolBacktestRunner
        with patch("axond.backtest_runner.AxonBacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {
                "final_nav": 110000.0, "total_pnl": 10000.0, "max_drawdown": 5000.0,
                "orders_accepted": 5, "orders_rejected": 0, "fills": 5,
            }
            MockEngine.return_value = mock_instance
            runner = MultiSymbolBacktestRunner({"initial_capital": 100000.0})
            runner.add_symbol("BTCUSDT", sample_df)
            runner.run()
            results = runner.get_results()
            assert "BTCUSDT" in results

    def test_get_portfolio_result(self, sample_df):
        from axond.backtest_runner import MultiSymbolBacktestRunner
        with patch("axond.backtest_runner.AxonBacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {
                "final_nav": 110000.0, "total_pnl": 10000.0, "max_drawdown": 5000.0,
                "orders_accepted": 5, "orders_rejected": 0, "fills": 5,
            }
            MockEngine.return_value = mock_instance
            runner = MultiSymbolBacktestRunner({"initial_capital": 100000.0})
            runner.add_symbol("BTCUSDT", sample_df)
            runner.add_symbol("ETHUSDT", sample_df)
            runner.run()
            portfolio = runner.get_portfolio_result()
            assert "total_pnl" in portfolio
            assert "final_nav" in portfolio
