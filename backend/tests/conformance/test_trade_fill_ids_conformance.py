"""上游引擎契约门禁:TradeRecord 的平仓 fill 关联形态(conformance)。

钉住 axon-quant(0.21.0 FLAT_TO_FLAT)的两条契约:
1. 引擎输出的 TradeRecord 必须含复数字段 `exit_fill_ids`(整个持仓周期的
   全部平仓 fill),`backtest_loop._format_round_trip_trades` 据此还原明细;
2. Python 层每条 round-trip trade 的 close fill 条数必须等于
   `exit_fill_ids` 长度(部分平仓聚合后 close fills 全部归属唯一 trade)。

背景(2026-10-21 踩坑):uv 对 maturin path 依赖的构建缓存不感知 .rs 源码
变化,`uv sync` 命中旧缓存把单数字段版本的 .so 装回 venv;因既有单测全部
mock 了 trades dict,旧 .so 逃过 216 个用例,close fill 关联静默变空。
本用例真跑引擎,环境 .so 过期时最先报警(本目录定位即引擎升级门禁)。

运行:`uv run pytest tests/conformance/test_trade_fill_ids_conformance.py -q`
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from backtest.backtest_loop import BacktestLoop
from backtest.strategy_loader_service import StrategyLoaderService

# 上游契约标记:断言钉住引擎 TradeRecord 契约,升级时最先受影响
pytestmark = [pytest.mark.upstream]


def _zigzag() -> pd.DataFrame:
    """正弦震荡行情:价格反复穿越均线 → dual_ma 反复开平仓。"""
    n = 200
    closes = [100.0 + 20.0 * math.sin(i / 5.0) for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        }
    )


def test_round_trip_close_fills_association() -> None:
    """每条 round-trip trade 的 close fill 条数 == len(exit_fill_ids) >= 1。

    旧 .so(单数 exit_fill_id)下 `tr.get("exit_fill_ids")` 为 None →
    close 关联退化为空列表,本断言即失败,直接暴露引擎环境过期。
    """
    strategy = StrategyLoaderService.load_strategy(
        strategy_name="dual_ma",
        strategy_params={},
        instrument_ids=[{"symbol": "BTCUSDT", "venue": "BINANCE"}],
        bar_types=["1h"],
    )
    assert strategy is not None

    loop = BacktestLoop(initial_cash=100_000.0)
    result = loop.run(strategy, _zigzag(), symbol="BTCUSDT")

    records = result.trade_records
    assert records, "zigzag 行情 dual_ma 应产生至少一条 round-trip trade"

    for t in records:
        close_n = sum(1 for f in t["fills"] if f["offset"] == "close")
        assert close_n >= 1, f"trade {t['trade_id']} 无 close fill,聚合异常"
        assert len(t["exit_fill_ids"]) == close_n, (
            f"trade {t['trade_id']} close 关联断裂:exit_fill_ids="
            f"{t['exit_fill_ids']} 但实有 {close_n} 条 close fill"
            "(疑似引擎 .so 过期或 exit_fill_ids 契约回退)"
        )
