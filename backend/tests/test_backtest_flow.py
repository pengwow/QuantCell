import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

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

@patch("collector.services.data_service.DataService.get_kline_data")
def test_backtest_complete_flow(mock_get_kline_data):
    """
    Test the complete backtest workflow with mocked data
    """
    # Mock Data Setup
    mock_data = []
    base_time = 1672531200000 # 2023-01-01
    price = 20000.0
    for i in range(100):
        mock_data.append({
            "timestamp": base_time + i * 86400000,
            "open": price,
            "high": price + 100,
            "low": price - 100,
            "close": price + (10 if i % 2 == 0 else -10),
            "volume": 1000.0
        })
        price = mock_data[-1]["close"]

    mock_get_kline_data.return_value = {
        "success": True,
        "kline_data": mock_data
    }

    strategy_name = "TestSmaCrossFlow"
    
    # 1. Upload Strategy
    print("\n[Step 1] Uploading Strategy...")
    response = client.post(
        "/api/strategy/upload",
        json={
            "strategy_name": strategy_name,
            "file_content": SAMPLE_STRATEGY,
            "description": "Automated test strategy for flow check",
            "version": "1.0.0"
        }
    )
    assert response.status_code == 200, f"Upload failed: {response.text}"
    assert response.json()["code"] == 0
    
    # 2. Run Backtest
    print("[Step 2] Running Backtest...")
    response = client.post(
        "/api/backtest/run",
        json={
            "strategy_config": {
                "strategy_name": strategy_name,
                "params": {"n1": 5, "n2": 10}
            },
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
                "start_time": "2023-01-01 00:00:00",
                "end_time": "2023-02-01 00:00:00",
                "initial_cash": 10000.0,
                "commission": 0.001
            }
        }
    )
    
    assert response.status_code == 200, f"Run backtest failed: {response.text}"
    run_data = response.json()
    result_data = run_data.get("data", {})
    
    if run_data["code"] != 0 or result_data.get("status") == "failed":
        message = result_data.get("message") if result_data else run_data.get("message")
        print(f"Backtest run warning: {message}")
        client.delete(f"/api/strategy/{strategy_name}")
        pytest.fail(f"Backtest run failed: {message}")

    backtest_id = result_data.get("task_id")
    assert backtest_id is not None, f"Task ID missing in success response: {result_data}"
    print(f"Backtest ID: {backtest_id}")
    
    # 3. Analyze Results
    print("[Step 3] Analyzing Results...")
    response = client.post(
        "/api/backtest/analyze",
        json={"backtest_id": backtest_id}
    )
    assert response.status_code == 200
    assert response.json()["code"] == 0
    
    # 4. Get Backtest Detail
    print("[Step 4] Getting Detail...")
    response = client.get(f"/api/backtest/{backtest_id}")
    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == backtest_id
    
    # 5. Get Replay Data
    print("[Step 5] Getting Replay Data...")
    response = client.get(f"/api/backtest/{backtest_id}/replay")
    assert response.status_code == 200
    assert response.json()["code"] == 0
    
    # 6. Delete Backtest
    print("[Step 6] Deleting Backtest...")
    response = client.delete(f"/api/backtest/delete/{backtest_id}")
    assert response.status_code == 200
    assert response.json()["code"] == 0
    
    # 7. Delete Strategy
    print("[Step 7] Deleting Strategy...")
    response = client.delete(f"/api/strategy/{strategy_name}")
    assert response.status_code == 200
    assert response.json()["code"] == 0
    
    print("Backtest Flow Test Completed Successfully.")
