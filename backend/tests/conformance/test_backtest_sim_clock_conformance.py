"""上游引擎契约门禁:回测成交审计时间 = 模拟时钟(conformance)。

钉住 axon-quant 0.16.1 的步进驱动时间戳修复:
apply_fill 生成 TradeRecord / entry_time_ns / fill NAV 曲线时必须用模拟时钟
(= set_clock 设定的 bar 事件时间),而非订单 created_at 的墙上时钟。

0.16.0 的症状:步进驱动(begin_bar + step,不走 run() 事件循环)下,
TradeRecord 的 timestamp_ns 全部记成回测运行当下时刻,与 bar 时间差数天以上。
本用例在 0.16.0 行为上必然失败(墙钟在数据窗口之外),是引擎二进制的
「真 0.16.1 行为探针」——版本号声明可能漂移(本地 path 依赖尤其如此),行为不会。

判别字段说明:result.trades 是唯一判别字段。fills_detail 从 0.7.0 起就一直
写 self.config.clock.now(),在 0.16.0/0.16.1 上语义相同,不能用于判别;
此处一并断言只为钉住 QuantCell round-trip 契约(fills_detail)的时间来源。

本目录是「引擎升级门禁」:axon-quant 升级时优先跑
(`uv run pytest tests/conformance/ -q`),全部通过再跑全量回归。
"""

from __future__ import annotations

import time

import pandas as pd
import pytest

from axon_bridge import BacktestEngine, spot_instrument

# 上游契约标记:断言钉住引擎成交审计时间来源,升级时最先受影响
pytestmark = [pytest.mark.upstream]

# 与 backtest_loop.BacktestLoop 保持一致的默认撮合/调仓参数
_INITIAL_CASH = 100_000.0
_HALF_SPREAD = 0.0005
_DEPTH_LEVELS = 5
_SIZE_PER_LEVEL = 100.0
_AUTO_REBALANCE_THRESHOLD = 0.001


def test_fill_audit_timestamp_uses_sim_clock() -> None:
    """步进驱动 round-trip:TradeRecord 时间必须落在数据窗口内,而非回测墙钟。

    三根日 bar,每根间隔 1 天:bar1 hold → bar2 买入开仓 → bar3 目标 0 平仓
    (TradeRecord 在平仓时创建,故需要完整 round-trip 才能观察到该字段)。
    bar 时间动态取 now-10d 起,保证数据窗口恒早于测试运行墙钟:
    0.16.0 把审计时间记成墙钟时会远晚于窗口末尾,断言必然失败。
    """
    # 数据窗口:now-10d / -9d / -8d,日 bar
    base = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=10)
    ts = [int((base + pd.Timedelta(days=i)).timestamp() * 1e9) for i in range(3)]
    ts_start, ts_end = ts[0], ts[-1]
    # 夹具前置条件:窗口整体早于墙钟,探针才有判别力
    assert ts_end < time.time_ns(), "数据窗口必须早于当前墙钟,否则探针失效"

    engine = (
        BacktestEngine(initial_cash=_INITIAL_CASH)
        .with_seed(42)
        .with_seed_liquidity(
            half_spread=_HALF_SPREAD,
            depth_levels=_DEPTH_LEVELS,
            size_per_level=_SIZE_PER_LEVEL,
        )
        .with_auto_rebalance(threshold=_AUTO_REBALANCE_THRESHOLD)
    )
    instrument = spot_instrument("BTC", "USDT")

    # 复刻 BacktestLoop 步进协议:set_clock → begin_bar → set_target_position
    # → rebalance_to_target → drain pending_events
    for i, price in enumerate((100.0, 101.0, 102.0)):
        engine.set_clock(ts[i])
        engine.begin_bar(price=price, instrument=instrument)
        if i == 1:
            engine.set_target_position(instrument, 10.0)  # bar2 买入开仓
        if i == 2:
            engine.set_target_position(instrument, 0.0)  # bar3 平仓
        engine.rebalance_to_target()
        while engine.pending_events > 0:
            engine.step()

    result = engine.run()

    # 成交前置检查:round-trip 必须产生 1 笔平仓 TradeRecord + 2 笔 fill
    assert len(result.trades) == 1, f"round-trip 应产生 1 笔 TradeRecord,got {len(result.trades)}"
    assert len(result.fills_detail) == 2, f"开+平应有 2 笔 fill,got {len(result.fills_detail)}"

    # 核心断言(0.16.0 上会失败):TradeRecord 时间 = 模拟时钟(bar 事件时间)
    trade_ts = int(result.trades[0]["timestamp_ns"])
    assert ts_start <= trade_ts <= ts_end, (
        f"TradeRecord.timestamp_ns={trade_ts} 落在数据窗口 [{ts_start}, {ts_end}] 之外,"
        f"像是墙上时钟(引擎 apply_fill 未用模拟时钟,0.16.0 行为)"
    )

    # 契约时间来源钉住:fills_detail 全部落在数据窗口内
    for f in result.fills_detail:
        fill_ts = int(f["timestamp_ns"])
        assert ts_start <= fill_ts <= ts_end, f"fill.timestamp_ns={fill_ts} 落在数据窗口之外,违反模拟时钟审计语义"
