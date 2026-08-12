"""BaselineBacktestService 测试 — 直接传 DataFrame,验证报告生成。"""
from pathlib import Path

import pandas as pd
import pytest

from backtest.baseline import BaselineBacktestService


@pytest.fixture
def trending_kline() -> pd.DataFrame:
    """200 根小时 K 线,稳定上涨,够 dual_ma 触发。"""
    dates = pd.date_range("2024-07-01", periods=200, freq="1h")
    closes = [100.0 + i * 0.5 for i in range(200)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * 200,
        },
        index=dates,
    )


def test_baseline_runs_and_writes_reports(tmp_path: Path, trending_kline: pd.DataFrame) -> None:
    """跑基线回测,产出 json + md。"""
    svc = BaselineBacktestService(
        strategy_name="momentum",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-10",
        output_dir=tmp_path,
        data=trending_kline,
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


def test_baseline_dual_ma_runs(tmp_path: Path, trending_kline: pd.DataFrame) -> None:
    """dual_ma 跑通。"""
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-10",
        output_dir=tmp_path,
        data=trending_kline,
    )
    report = svc.run()
    assert report.template == "dual_ma"
    assert report.total_trades >= 0


def test_baseline_empty_data_raises(tmp_path: Path) -> None:
    """K 线为空 → ValueError。"""
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-10",
        output_dir=tmp_path,
        data=pd.DataFrame(),
    )
    with pytest.raises(ValueError):
        svc.run()
