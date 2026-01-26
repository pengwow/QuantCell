import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from backtest.service import BacktestService

client = TestClient(app)

# Sample Strategy Content
SAMPLE_STRATEGY = """
from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd

class TestSmaCrossFlow(Strategy):
    n1 = 10
    n2 = 20
    
    def init(self):
        if len(self.data) < 2:
            return
        close = pd.Series(self.data.Close)
        self.sma1 = self.I(lambda x: pd.Series(x).rolling(self.n1).mean(), close)
        self.sma2 = self.I(lambda x: pd.Series(x).rolling(self.n2).mean(), close)
    
    def next(self):
        if len(self.data) < 20:
            return
        if crossover(self.sma1, self.sma2):
            self.buy()
        elif crossover(self.sma2, self.sma1):
            self.sell()
"""

@pytest.fixture
def mock_kline_data():
    """
    Create mock kline data for testing
    """
    def generate_data(base_price, base_time, count=100):
        mock_data = []
        price = base_price
        for i in range(count):
            mock_data.append({
                "timestamp": base_time + i * 86400000,
                "open": price,
                "high": price + 100,
                "low": price - 100,
                "close": price + (10 if i % 2 == 0 else -10),
                "volume": 1000.0
            })
            price = mock_data[-1]["close"]
        return mock_data
    
    return generate_data

@patch("collector.services.data_service.DataService.get_kline_data")
@patch("strategy.service.StrategyService.load_strategy")
def test_multi_currency_backtest(mock_load_strategy, mock_get_kline_data, mock_kline_data):
    """
    Test multi-currency backtest functionality
    """
    # Mock the strategy loading
    from backtesting import Strategy
    # 使用一个会产生交易的策略类
    class MockStrategy(Strategy):
        def init(self):
            pass
        def next(self):
            # 简单策略：每根K线都买入和卖出，确保产生交易
            if not self.position:
                self.buy(size=0.1)
            else:
                self.sell()
    mock_load_strategy.return_value = MockStrategy
    
    # Mock Data Setup for multiple currencies
    def mock_get_kline_data_side_effect(symbol, *args, **kwargs):
        base_prices = {
            "BTCUSDT": 20000.0,
            "ETHUSDT": 1500.0,
            "BNBUSDT": 300.0
        }
        
        base_price = base_prices.get(symbol, 1000.0)
        base_time = 1672531200000  # 2023-01-01
        
        return {
            "kline_data": mock_kline_data(base_price, base_time)
        }
    
    mock_get_kline_data.side_effect = mock_get_kline_data_side_effect
    
    # Create BacktestService instance and test directly
    from backtest.service import BacktestService
    backtest_service = BacktestService()
    
    # Run Multi-Currency Backtest directly using service method
    result = backtest_service.run_backtest(
        strategy_config={
            "strategy_name": "TestStrategy",
            "params": {}
        },
        backtest_config={
            "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-02-01 00:00:00",
            "initial_cash": 10000.0,
            "commission": 0.001
        }
    )
    
    # Verify multi-currency result structure
    assert result.get("status") == "success"
    assert "summary" in result
    assert "currencies" in result
    assert "successful_currencies" in result
    assert "failed_currencies" in result
    
    # Check summary statistics
    summary = result["summary"]
    assert summary["total_currencies"] == 3
    assert summary["successful_currencies"] == 3
    assert summary["failed_currencies"] == 0
    
    # Check that all currencies are in results
    currencies = result["currencies"]
    assert "BTCUSDT" in currencies
    assert "ETHUSDT" in currencies
    assert "BNBUSDT" in currencies
    
    # Check that each currency has successful results
    for symbol, result in currencies.items():
        assert result.get("status") == "success"
        assert "metrics" in result
        assert "trades" in result
        assert "equity_curve" in result
    
    print("Multi-Currency Backtest Test Completed Successfully.")

def test_result_merge_algorithm():
    """
    Test the result merging algorithm directly
    """
    # Create mock results for multiple currencies
    mock_results = {
        "BTCUSDT": {
            "status": "success",
            "strategy_name": "TestStrategy",
            "backtest_config": {"initial_cash": 10000},
            "metrics": [
                {"name": "Return [%]", "value": 15.5},
                {"name": "Max. Drawdown [%]", "value": -5.4},
                {"name": "Sharpe Ratio", "value": 1.2},
                {"name": "Win Rate [%]", "value": 60.0},
                {"name": "Profit Factor", "value": 1.8},
                {"name": "Equity Final [$]", "value": 11550.0}
            ],
            "trades": [{}, {}, {}]  # 3 trades
        },
        "ETHUSDT": {
            "status": "success",
            "strategy_name": "TestStrategy",
            "backtest_config": {"initial_cash": 10000},
            "metrics": [
                {"name": "Return [%]", "value": 10.2},
                {"name": "Max. Drawdown [%]", "value": -3.2},
                {"name": "Sharpe Ratio", "value": 1.5},
                {"name": "Win Rate [%]", "value": 65.0},
                {"name": "Profit Factor", "value": 2.1},
                {"name": "Equity Final [$]", "value": 11020.0}
            ],
            "trades": [{}, {}, {}, {}]  # 4 trades
        },
        "BNBUSDT": {
            "status": "success",
            "strategy_name": "TestStrategy",
            "backtest_config": {"initial_cash": 10000},
            "metrics": [
                {"name": "Return [%]", "value": 8.7},
                {"name": "Max. Drawdown [%]", "value": -4.1},
                {"name": "Sharpe Ratio", "value": 0.9},
                {"name": "Win Rate [%]", "value": 55.0},
                {"name": "Profit Factor", "value": 1.5},
                {"name": "Equity Final [$]", "value": 10870.0}
            ],
            "trades": [{}, {}]  # 2 trades
        }
    }
    
    # Create BacktestService instance and test merge algorithm
    backtest_service = BacktestService()
    merged_result = backtest_service.merge_backtest_results(mock_results)
    
    # Verify merged result structure
    assert merged_result["status"] == "success"
    assert "summary" in merged_result
    assert "currencies" in merged_result
    
    # Verify summary calculations
    summary = merged_result["summary"]
    assert summary["total_currencies"] == 3
    assert summary["successful_currencies"] == 3
    assert summary["failed_currencies"] == 0
    assert summary["total_trades"] == 9  # 3 + 4 + 2
    assert summary["total_initial_cash"] == 30000  # 10000 * 3
    assert summary["total_equity"] == 33440.0  # 11550 + 11020 + 10870
    
    # Verify average calculations
    assert summary["average_return"] == pytest.approx(11.47, rel=0.01)  # (15.5 + 10.2 + 8.7) / 3
    assert summary["average_max_drawdown"] == pytest.approx(-4.23, rel=0.01)  # (-5.4 + -3.2 + -4.1) / 3
    assert summary["average_sharpe_ratio"] == pytest.approx(1.2, rel=0.01)  # (1.2 + 1.5 + 0.9) / 3
    assert summary["average_win_rate"] == pytest.approx(60.0, rel=0.01)  # (60 + 65 + 55) / 3
    
    # Verify total return calculation
    assert summary["total_return"] == pytest.approx(11.47, rel=0.01)  # (33440 - 30000) / 30000 * 100
    
    print("Result Merge Algorithm Test Completed Successfully.")

@patch("collector.services.data_service.DataService.get_kline_data")
@patch("strategy.service.StrategyService.load_strategy")
def test_multi_currency_with_some_failed(mock_load_strategy, mock_get_kline_data, mock_kline_data):
    """
    Test multi-currency backtest with some failed currencies
    """
    # Mock the strategy loading
    from backtesting import Strategy
    # 使用一个会产生交易的策略类
    class MockStrategy(Strategy):
        def init(self):
            pass
        def next(self):
            # 简单策略：每根K线都买入和卖出，确保产生交易
            if not self.position:
                self.buy(size=0.1)
            else:
                self.sell()
    mock_load_strategy.return_value = MockStrategy
    
    def mock_get_kline_data_side_effect(symbol, *args, **kwargs):
        if symbol == "FAILEDUSDT":
            return {
                "kline_data": []
            }
        
        return {
            "kline_data": mock_kline_data(1000.0, 1672531200000)
        }
    
    mock_get_kline_data.side_effect = mock_get_kline_data_side_effect
    
    # Create BacktestService instance and test directly
    from backtest.service import BacktestService
    backtest_service = BacktestService()
    
    # Run Multi-Currency Backtest directly using service method
    result = backtest_service.run_backtest(
        strategy_config={
            "strategy_name": "TestStrategy",
            "params": {}
        },
        backtest_config={
            "symbols": ["BTCUSDT", "FAILEDUSDT", "ETHUSDT"],
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-02-01 00:00:00",
            "initial_cash": 10000.0,
            "commission": 0.001
        }
    )
    
    # Verify summary shows mixed results
    assert result.get("status") == "success"
    summary = result["summary"]
    assert summary["total_currencies"] == 3
    assert summary["successful_currencies"] == 2
    assert summary["failed_currencies"] == 1
    
    # Verify failed currency is in the results
    currencies = result["currencies"]
    assert "FAILEDUSDT" in currencies
    assert currencies["FAILEDUSDT"]["status"] == "failed"
    
    # Verify successful currencies are processed
    assert "BTCUSDT" in currencies
    assert currencies["BTCUSDT"]["status"] == "success"
    assert "ETHUSDT" in currencies
    assert currencies["ETHUSDT"]["status"] == "success"
    
    print("Multi-Currency with Failed Currencies Test Completed Successfully.")

def test_data_isolation():
    """
    Test that each currency's backtest is isolated from others
    """
    # This test verifies that the data manager is properly isolated per currency
    # by checking that each backtest run gets its own data manager instance
    
    from backtest.data_manager import DataManager
    from collector.services.data_service import DataService
    
    # Create separate data managers for different currencies
    data_service = DataService()
    dm1 = DataManager(data_service)
    dm2 = DataManager(data_service)
    
    # Verify they are different instances
    assert dm1 is not dm2
    
    # Verify each has its own cache
    assert dm1.data_cache is not dm2.data_cache
    
    # Test that adding data to one doesn't affect the other
    dm1.data_cache["BTCUSDT"] = {"1d": "test_data"}
    assert "BTCUSDT" not in dm2.data_cache
    
    print("Data Isolation Test Completed Successfully.")
