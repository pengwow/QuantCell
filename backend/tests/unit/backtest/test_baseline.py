"""BaselineBacktestService 测试 — 用 mock ParquetDataProvider 验证流程。"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# quality.data_provider 已删除,需先注入 mock 才能导入 backtest.baseline
if "quality.data_provider" not in sys.modules:
    sys.modules["quality.data_provider"] = MagicMock()
if "quality.parquet_provider" not in sys.modules:
    sys.modules["quality.parquet_provider"] = MagicMock()

from backtest.baseline import BaselineBacktestService  # noqa: E402


@pytest.fixture
def mock_kline():
    """Mock 1 年 1h K 线 (8760 根) + 强烈上涨趋势。"""
    dates = pd.date_range("2024-07-01", periods=200, freq="1h")
    closes = [100.0 + i * 0.5 for i in range(200)]  # 100 → 200
    return pd.DataFrame({
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000.0] * 200,
    }, index=dates)


def test_baseline_runs_and_writes_reports(tmp_path, mock_kline):
    """跑基线回测,产出 json + md。"""
    with patch("backtest.baseline.ParquetDataProvider") as MockProvider:
        instance = MockProvider.return_value
        instance.get_kline_data.return_value = mock_kline

        svc = BaselineBacktestService(
            strategy_name="momentum",
            symbol="BTCUSDT",
            start="2024-07-01",
            end="2024-07-10",
            output_dir=tmp_path,
        )
        report = svc.run()

        assert report.template == "momentum"
        assert report.symbol == "BTCUSDT"
        # json + md 存在
        json_files = list(tmp_path.glob("*.json"))
        md_files = list(tmp_path.glob("*.md"))
        assert len(json_files) == 1
        assert len(md_files) == 1
        # json 内容
        import json
        data = json.loads(json_files[0].read_text())
        assert data["template"] == "momentum"
        assert "total_pnl" in data


def test_baseline_dual_ma_runs(tmp_path, mock_kline):
    """dual_ma 跑通。"""
    with patch("backtest.baseline.ParquetDataProvider") as MockProvider:
        instance = MockProvider.return_value
        instance.get_kline_data.return_value = mock_kline

        svc = BaselineBacktestService(
            strategy_name="dual_ma",
            symbol="BTCUSDT",
            start="2024-07-01",
            end="2024-07-10",
            output_dir=tmp_path,
        )
        report = svc.run()
        assert report.template == "dual_ma"
        assert report.total_trades >= 0


def test_baseline_empty_data_raises(tmp_path):
    """K 线为空 → ValueError。"""
    with patch("backtest.baseline.ParquetDataProvider") as MockProvider:
        instance = MockProvider.return_value
        instance.get_kline_data.return_value = pd.DataFrame()

        svc = BaselineBacktestService(
            strategy_name="dual_ma",
            symbol="BTCUSDT",
            start="2024-07-01",
            end="2024-07-10",
            output_dir=tmp_path,
        )
        with pytest.raises(ValueError):
            svc.run()
