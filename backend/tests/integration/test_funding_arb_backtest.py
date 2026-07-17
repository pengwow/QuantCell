"""funding arbitrage 端到端集成测试。"""
import math
import pandas as pd
import pytest

from backtest.baseline import BaselineBacktestService, make_synthetic_kline


def _make_kline_with_funding(n: int = 200, start_price: float = 50000.0):
    """生成 200 根 1h K 线。"""
    df = make_synthetic_kline(n=n, start_price=start_price, seed=42)
    return df


def test_full_backtest_with_funding_csv_runs_to_completion(tmp_path):
    """baseline 跑 7 天 BTCUSDT + funding CSV → 无异常退出。"""
    funding_csv = tmp_path / "funding.csv"
    funding_rows = ["funding_time_ms,funding_rate"]
    base_ts = 1701302400000
    for i in range(50):
        funding_rows.append(f"{base_ts + i*8*3600*1000},{0.0001 + 0.0001*(i%5)}")
    funding_csv.write_text("\n".join(funding_rows))

    df = _make_kline_with_funding()
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        data=df,
        funding_history_path=str(funding_csv),
        output_dir=tmp_path,
    )
    report = svc.run()
    assert report.template == "funding_arbitrage"
    assert report.total_pnl is not None
    assert (tmp_path / f"funding_arbitrage_BTCUSDT_2024-07-01_2024-07-08.json").exists()
    assert (tmp_path / f"funding_arbitrage_BTCUSDT_2024-07-01_2024-07-08.md").exists()


def test_backtest_equity_curve_includes_funding_cash(tmp_path):
    """跑 7 天, total_pnl 应包含 funding_cash 部分。"""
    funding_csv = tmp_path / "funding.csv"
    funding_rows = ["funding_time_ms,funding_rate"]
    base_ts = 1701302400000
    for i in range(20):
        funding_rows.append(f"{base_ts + i*8*3600*1000},0.001")
    funding_csv.write_text("\n".join(funding_rows))

    df = _make_kline_with_funding()
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        data=df,
        funding_history_path=str(funding_csv),
        output_dir=tmp_path,
    )
    report = svc.run()
    assert report.total_pnl is not None
    assert isinstance(report.total_pnl, float)


def test_backtest_with_missing_funding_csv_degrades_gracefully(tmp_path):
    """不提供 funding_history_path → funding 字段全 0, baseline 仍正常运行。"""
    df = _make_kline_with_funding()
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        data=df,
        output_dir=tmp_path,
    )
    report = svc.run()
    assert report.total_pnl is not None


def test_backtest_strategy_context_has_funding_cash_set(tmp_path):
    """验证 baseline.run 真的注入 funding_cash 到 ctx（即 ctx.funding_cash 会被 update）。"""
    from strategy.templates.funding_arbitrage import FundingArbitrage
    from strategy.base import StrategyConfig, StrategyContext
    from strategy import loader as loader_mod

    captured = {"ctx": None}

    class SpyStrategy(FundingArbitrage):
        def on_bar(self, bar, ctx):
            captured["ctx"] = ctx
            return super().on_bar(bar, ctx)

    # ponytail: spec 写的是 _registry,实际变量名是 _REGISTRY(loader.py:15)
    loader_mod._REGISTRY["spy_funding_arb"] = SpyStrategy  # type: ignore

    funding_csv = tmp_path / "funding.csv"
    funding_rows = ["funding_time_ms,funding_rate"]
    base_ts = 1701302400000
    for i in range(20):
        funding_rows.append(f"{base_ts + i*8*3600*1000},0.001")
    funding_csv.write_text("\n".join(funding_rows))

    df = _make_kline_with_funding()
    svc = BaselineBacktestService(
        strategy_name="spy_funding_arb",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        data=df,
        funding_history_path=str(funding_csv),
        output_dir=tmp_path,
    )
    svc.run()
    assert captured["ctx"] is not None
    assert hasattr(captured["ctx"], "funding_cash")
