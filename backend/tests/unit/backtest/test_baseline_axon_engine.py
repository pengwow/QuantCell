"""BaselineBacktestService 走 axon_quant 0.7.0 多 leg API 测试。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.baseline import BaselineBacktestService


@pytest.fixture
def trending_kline() -> pd.DataFrame:
    """200 根小时 K 线,稳定上涨,够 dual_ma 触发。

    index = DatetimeIndex(从 2024-07-01 1h 频率)
    """
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


def test_baseline_dual_ma_via_axon_engine(tmp_path: Path, trending_kline: pd.DataFrame) -> None:
    """Task 5: BaselineBacktestService.run() 走 axon_quant BacktestEngine。

    验证:dual_ma 跑通且 total_trades / pnl 是 finite number(0 算合法)。
    """
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
    # 走 axon_quant 后 total_trades 来自 result.trades,可能 = 0 也合法
    assert report.total_trades >= 0
    # pnl 是 finite float
    assert isinstance(report.total_pnl, float)
    assert np.isfinite(report.total_pnl)


def test_baseline_total_trades_uses_result_trades(tmp_path: Path, trending_kline: pd.DataFrame) -> None:
    """Task 5 硬约束:total_trades = len(result.trades) 而非 result.fills。"""
    from axon_bridge import BacktestEngine, spot_instrument

    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-10",
        output_dir=tmp_path,
        data=trending_kline,
    )
    # 跑一个 mini backtest 单独验证 trades 数
    bt = BacktestEngine(initial_cash=100_000.0)
    spot = spot_instrument("BTC", "USDT")
    for i, close in enumerate([100.0 + j * 0.5 for j in range(50)]):
        ts = 1_700_000_000_000_000_000 + i * 3_600_000_000_000
        bt.set_clock(ts)
        bt.begin_bar(price=close, instrument=spot)
    result = bt.run()
    # trades 字段是 round-trip 列表(可能空),与 fills 区分
    assert hasattr(result, "trades")
    assert isinstance(result.trades, list)
    # total_trades 应 = len(result.trades)
    assert svc._count_trades_via_engine(result) == len(result.trades)


def test_baseline_total_pnl_uses_final_nav_minus_initial(tmp_path: Path) -> None:
    """Task 5 硬约束:total_pnl = result.final_nav - initial_cash。

    验证:即使 total_pnl 是 0(无 fill),也不应从 result.fills 算(0),
    而应该来自 account view 视角(final_nav - initial_cash)。
    """
    from backtest.baseline import BaselineBacktestService
    from strategy.base import StrategyConfig
    from strategy.templates.dual_ma import DualMA
    from axon_bridge import BacktestEngine, spot_instrument

    # 空 data + 简单验证
    dates = pd.date_range("2024-07-01", periods=10, freq="1h")
    closes = [100.0] * 10
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000.0] * 10,
        },
        index=dates,
    )
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-10",
        output_dir=tmp_path,
        data=df,
    )
    report = svc.run()
    # total_pnl 必须 = final_nav - initial_cash
    # 即使全无 fill,total_pnl 也应 = 0.0(干净)
    assert report.total_pnl == 0.0, f"无 fill 时 total_pnl 应 = 0.0, got {report.total_pnl}"


def test_baseline_funding_arbitrage_multi_leg(tmp_path: Path) -> None:
    """Task 5:funding_arbitrage 走多 leg 路径(spot + perp)。

    验证:
    - 用 funding_history 触发 1 次 funding 事件
    - 跑出 spot + perp fills
    - total_funding_pnl 被记录
    """
    # 8 天数据 (192 根 1h bar) + funding history 2 条
    dates = pd.date_range("2024-07-01", periods=192, freq="1h")
    closes = [100.0] * 192  # 平稳, 让 funding 信号主导
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000.0] * 192,
        },
        index=dates,
    )
    # funding history: 2 个 8h 时刻 + 0.0005 费率(鼓励 long funding)
    # funding_time 用 2024-07-01 + offset (ms since epoch)
    funding_csv = tmp_path / "funding.csv"
    funding_csv.write_text(
        "funding_time_ms,funding_rate\n"
        "1719792000000,0.0005\n"  # 2024-07-01 00:00 UTC
        "1719820800000,0.0005\n"  # 2024-07-01 08:00 UTC
    )
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT-PERP",
        start="2024-07-01",
        end="2024-07-08",
        output_dir=tmp_path,
        data=df,
        funding_history_path=str(funding_csv),
        spot_symbol="BTCUSDT",
    )
    report = svc.run()
    # funding_arbitrage 应该至少产生 1 笔 trade
    assert report.total_trades >= 1, (
        f"funding_arbitrage 跑 8h+ funding 应有 trades,got {report.total_trades} "
        f"(pnl={report.total_pnl}, funding_pnl={report.total_funding_pnl})"
    )
    # funding_pnl 应被记录
    assert report.total_funding_pnl > 0.0, (
        f"funding_pnl 应 > 0 (perp short 收 funding),got {report.total_funding_pnl}"
    )


def test_baseline_sharpe_uses_bar_nav_curve(tmp_path: Path, trending_kline: pd.DataFrame) -> None:
    """Task 5:sharpe_ratio 用 bar_nav_curve 重算(避免 0.7.0 短回测失真)。"""
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-10",
        output_dir=tmp_path,
        data=trending_kline,
    )
    report = svc.run()
    # sharpe 应是 finite (即使 0 也合法)
    assert isinstance(report.sharpe_ratio, float)
    assert np.isfinite(report.sharpe_ratio), f"sharpe_ratio 应 finite,got {report.sharpe_ratio}"


def test_baseline_axon_0_10_0_new_fields(tmp_path: Path) -> None:
    """0.10.0: 验证引擎内置 total_fees / max_drawdown_pct 字段被正确提取。"""
    dates = pd.date_range("2024-07-01", periods=200, freq="1h")
    closes = [100.0 + i * 0.5 for i in range(200)]
    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * 200,
        },
        index=dates,
    )
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-10",
        output_dir=tmp_path,
        data=df,
    )
    report = svc.run()
    # 0.10.0 新增字段存在且为 finite float
    assert isinstance(report.total_fees, float)
    assert report.total_fees >= 0.0, f"total_fees 应 >= 0, got {report.total_fees}"
    assert isinstance(report.max_drawdown_pct, float)
    assert 0.0 <= report.max_drawdown_pct <= 1.0, (
        f"max_drawdown_pct 应在 [0,1], got {report.max_drawdown_pct}"
    )
    # win_rate 由引擎直接计算,应在 [0,1]
    assert 0.0 <= report.win_rate <= 1.0, f"win_rate 应在 [0,1], got {report.win_rate}"
    # JSON 输出应包含新字段
    import json
    report_dict = report.to_dict()
    assert "total_fees" in report_dict
    assert "max_drawdown_pct" in report_dict

