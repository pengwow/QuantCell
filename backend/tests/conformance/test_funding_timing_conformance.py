"""上游引擎契约门禁:funding 拨付时序(conformance)。

钉住 BaselineBacktestService.run() 的 per-bar 事件顺序契约:
begin_bar → on_bar → set_target_position(× N legs) → rebalance_to_target
→ push_funding(可选) → step()。

时序错乱的典型症状(0.7.x 曾发生):push_funding 早于 rebalance 时读到
position=0,total_funding_pnl 恒为 0。该用例是 funding 链路的端到端哨兵,
引擎升级改变事件分发时机时最先报警。

本目录是「引擎升级门禁」:axon-quant 升级时优先跑
(`uv run pytest tests/conformance/ -q`),全部通过再跑全量回归。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from backtest.baseline import BaselineBacktestService

if TYPE_CHECKING:
    from pathlib import Path

# 上游契约标记:断言钉住引擎 funding dispatch 时机,升级时最先受影响
pytestmark = [pytest.mark.upstream]


def test_funding_dispatch_timing_multi_leg(tmp_path: Path) -> None:
    """funding 时序契约:平稳行情下 funding 事件触发 → spot+perp 双腿建仓 → funding_pnl 入账。

    验证三点:
    - funding_history 触发 funding 事件后产生双腿 trades(≥1);
    - perp short 收 funding → total_funding_pnl > 0(时序正确才可能累计);
    - 若 push_funding 时序错乱(读到 position=0),funding_pnl 会恒 0,此断言即失败。
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
    # funding_pnl 应被记录:perp short 收 funding,时序正确时 > 0
    assert report.total_funding_pnl > 0.0, f"funding_pnl 应 > 0 (perp short 收 funding),got {report.total_funding_pnl}"
