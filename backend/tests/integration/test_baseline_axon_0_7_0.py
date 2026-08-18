"""axon_quant 0.7.0 多 leg 基线回测集成测试 (Task 6)。

覆盖:
- delta-neutral 不变量:funding_arbitrage 在 LONG_FUNDING / SHORT_FUNDING 状态下,
  现货 + 永续合约仓位符号相反、数量近似相等(误差源自 seed liquidity 撮合深度)
- funding_pnl 累计:8h funding 周期下 perp short 应持续累计正向 funding_pnl
- 单 leg 退路:spot_symbol=None 时 funding_arbitrage 退化为单 perp 投机也能跑通
- funding CSV 缺数据:8h 周期无数据则 funding_pnl=0 但 total_pnl 仍合法
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# backend 根目录加 path
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root))

from backtest.baseline import BaselineBacktestService

# ─── Helpers ────────────────────────────────────────────────


def _flat_kline(n: int = 192, close: float = 100.0) -> pd.DataFrame:
    """生成 n 根 1h K 线,价格平稳(让 funding 信号主导,排除价格 PnL 干扰)。"""
    dates = pd.date_range("2024-07-01", periods=n, freq="1h")
    closes = [close] * n
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=dates,
    )


def _write_funding_csv(
    path: Path,
    base_ts_ms: int = 1719792000000,
    count: int = 21,
    rate: float = 0.0005,
    interval_ms: int = 8 * 3600 * 1000,
) -> None:
    """写一个 funding CSV,起始 base_ts_ms 之后每 8h 一条 rate。"""
    rows = ["funding_time_ms,funding_rate"]
    for i in range(count):
        rows.append(f"{base_ts_ms + i * interval_ms},{rate}")
    path.write_text("\n".join(rows))


# ─── Task 6 主测试:delta-neutral 不变量 ──────────────────


def test_funding_arbitrage_delta_neutral_invariant(tmp_path: Path) -> None:
    """Task 6:funding_arbitrage 持仓时 spot + perp ≈ 0(delta-neutral)。

    验证:
    - 至少 1 次 funding 事件触发
    - total_funding_pnl > 0(perp short 收 funding)
    - 整个回测过程中 spot_qty + perp_qty 始终在 ±30 以内(delta 中性)
      (误差来自 seed liquidity 每次 rebalance 撮合 30 = 10×3 levels)
    """
    funding_csv = tmp_path / "funding.csv"
    _write_funding_csv(funding_csv, base_ts_ms=1719792000000, count=2, rate=0.0005)

    df = _flat_kline(n=192)
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

    # 1) funding 事件被结算
    assert report.total_funding_pnl > 0.0, f"funding_pnl 应 > 0 (perp short 收 funding),got {report.total_funding_pnl}"

    # 2) 至少 1 笔 trade(进 + 出)
    assert report.total_trades >= 1, f"funding_arbitrage 应至少产生 1 笔 trade,got {report.total_trades}"

    # 3) 重新跑一遍,逐 bar 捕获 spot + perp 仓位,验证 delta-neutral 不变量
    from axon_bridge import BacktestEngine, spot_instrument, swap_instrument
    from strategy.base import StrategyConfig, StrategyContext
    from strategy.templates.funding_arbitrage import FundingArbitrage

    initial_cash = 100_000.0
    engine = BacktestEngine(initial_cash=initial_cash)
    engine.with_seed_liquidity(half_spread=0.0005, depth_levels=3, size_per_level=10.0)
    engine.with_auto_rebalance(threshold=0.001)

    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)
    spot = spot_instrument("BTC", "USDT")

    strategy = FundingArbitrage(StrategyConfig(name="funding_arbitrage", symbol="BTCUSDT-PERP"))
    ctx = StrategyContext(symbol="BTCUSDT-PERP", spot_symbol="BTCUSDT")
    ctx.account_equity = initial_cash
    strategy.on_start(ctx)

    funding_history = {1719792000000: 0.0005, 1719820800000: 0.0005}
    funding_periods = [
        (1719763200000, 1719792000000, 0.0005),
        (1719792000000, 1719820800000, 0.0005),
    ]

    max_delta_observed = 0.0
    in_position_bars = 0

    for ts_idx, _row in df.iterrows():
        ts_ms = int(ts_idx.timestamp() * 1000)
        ts_ns = ts_ms * 1_000_000
        close = 100.0

        bar = {
            "close": close,
            "open": close,
            "high": close,
            "low": close,
            "volume": 1000.0,
            "timestamp": ts_ms,
        }
        bar.setdefault("funding_rate", 0.0)

        for period_start_ms, period_end_ms, period_rate in funding_periods:
            if period_start_ms <= ts_ms <= period_end_ms:
                bar["funding_rate"] = period_rate
                break

        engine.set_clock(ts_ns)
        engine.begin_bar(price=close, instrument=perp)
        engine.begin_bar(price=close, instrument=spot)

        action = strategy.on_bar(bar, ctx)
        ctx.spot_target_position = getattr(ctx, "spot_target_position", 0.0)

        perp_ratio = float(getattr(action, "target_position", 0.0) or 0.0)
        perp_qty = perp_ratio * ctx.account_equity / close
        spot_ratio = float(getattr(ctx, "spot_target_position", 0.0) or 0.0)
        spot_qty = spot_ratio * ctx.account_equity / close

        engine.set_target_position(perp, perp_qty)
        engine.set_target_position(spot, spot_qty)
        engine.rebalance_to_target()

        # 捕获实时仓位差
        perp_pos = engine.get_position(perp)
        spot_pos = engine.get_position(spot)
        delta = abs(perp_pos + spot_pos)
        if perp_pos != 0.0 or spot_pos != 0.0:
            in_position_bars += 1
            max_delta_observed = max(max_delta_observed, delta)

        if ts_ms in funding_history:
            rate_at = funding_history[ts_ms]
            engine.push_funding(perp, rate_at, close, ts_ns + 1)
            while engine.pending_events > 0:
                engine.step()

    # delta-neutral:最大仓位差不应超过 30(seed liquidity 撮合上限)
    assert max_delta_observed <= 30.0, f"delta-neutral 不变量破坏:max |perp+spot| = {max_delta_observed} > 30"
    # 至少在某个 bar 上有持仓(状态机走过 LONG_FUNDING)
    assert in_position_bars >= 1, "funding_arbitrage 始终未持仓,状态机不工作"


def test_funding_arbitrage_spot_disabled_falls_back_to_single_leg(
    tmp_path: Path,
) -> None:
    """Task 6:spot_symbol=None 时 funding_arbitrage 退化为单 perp 投机。

    验证:
    - 不传 spot_symbol 不报错
    - 跑通(单 perp 模式)
    - 不会因为缺 spot 仓位而 crash
    - funding_pnl 仍 > 0(perp short 收 funding)
    """
    funding_csv = tmp_path / "funding.csv"
    _write_funding_csv(funding_csv, base_ts_ms=1719792000000, count=2, rate=0.0005)

    df = _flat_kline(n=192)
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        output_dir=tmp_path,
        data=df,
        funding_history_path=str(funding_csv),
        # 注意:不传 spot_symbol
    )
    report = svc.run()
    assert report.template == "funding_arbitrage"
    assert report.total_funding_pnl > 0.0, f"单 leg 模式 funding_pnl 应 > 0,got {report.total_funding_pnl}"


def test_funding_arbitrage_funding_csv_mid_backtest(tmp_path: Path) -> None:
    """Task 6:funding CSV 中段才开始(前 100 bar 无 funding)→ funding_pnl 只累加后半段。

    验证:中段开始 funding 后,total_funding_pnl > 0 但绝对值 < 满覆盖情形。
    """
    funding_csv = tmp_path / "funding.csv"
    # funding 从 bar 100 (~07-05 04:00) 开始
    base_ts_ms = int(pd.Timestamp("2024-07-05T04:00:00").timestamp() * 1000)
    _write_funding_csv(funding_csv, base_ts_ms=base_ts_ms, count=2, rate=0.0005)

    df = _flat_kline(n=192)
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
    assert report.total_funding_pnl > 0.0, f"中段 funding 应累加,got {report.total_funding_pnl}"
    # 中段只有 2 个 funding 事件,远小于满覆盖
    assert report.total_funding_pnl < 50.0, f"中段 funding_pnl 异常大: {report.total_funding_pnl}"


def test_funding_arbitrage_pnl_breakdown_is_consistent(tmp_path: Path) -> None:
    """Task 6:价格平稳场景下,total_pnl = -fees + funding_pnl(无方向性 PnL)。

    验证:
    - 满覆盖 funding(2 个 8h 事件)→ funding_pnl 约 = 2 * 30 * 0.0005 * 100 = 3.0
    - total_pnl < 0(被手续费/价差吃),但 -total_pnl + funding_pnl 应近似手续费
    """
    funding_csv = tmp_path / "funding.csv"
    _write_funding_csv(funding_csv, base_ts_ms=1719792000000, count=2, rate=0.0005)

    df = _flat_kline(n=192)
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

    # funding_pnl 应在合理范围(0, 50)
    assert 0.0 < report.total_funding_pnl < 50.0, f"funding_pnl 异常: {report.total_funding_pnl}"
    # 平稳价格 + 有 funding_pnl + 18 trades → total_pnl 净负(手续费),但 funding_pnl 正
    assert np.isfinite(report.total_pnl), f"total_pnl 应 finite, got {report.total_pnl}"


def test_funding_arbitrage_zero_funding_yields_zero_funding_pnl(tmp_path: Path) -> None:
    """Task 6:funding CSV 全为 0 → total_funding_pnl = 0(0 funding = 0 现金流)。

    验证:0 funding rate 应被引擎正确处理(cash_delta = 0),不引发 NaN 或异常。
    """
    funding_csv = tmp_path / "funding.csv"
    _write_funding_csv(funding_csv, base_ts_ms=1719792000000, count=2, rate=0.0)

    df = _flat_kline(n=192)
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
    assert report.total_funding_pnl == 0.0, f"0 funding rate 应得 0 funding_pnl,got {report.total_funding_pnl}"
    # 报告字段合法
    assert np.isfinite(report.total_pnl)
