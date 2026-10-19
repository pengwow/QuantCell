"""round-trip 成交契约测试：锁死 _format_round_trip_trades 的输出字段集与语义。

前端三个回测页（详情/单品种回放/全局回放）都按该契约渲染，
字段集一旦漂移（如再混入大写兼容字段）此处立即失败。

配对逻辑已下沉到 axon_quant 引擎(apply_fill 6 状态机),本方法只做字段映射:
引擎 result.trades(含 entry_price/entry_time_ns/realized_pnl/net_quantity)
→ 前端 15 字段契约。
"""

from __future__ import annotations

from backtest.backtest_loop import BacktestLoop

# 契约定稿字段全集（15 个，小写）
CONTRACT_FIELDS = {
    "trade_id",
    "symbol",
    "timestamp",
    "formatted_time",
    "entry_time",
    "exit_time",
    "exit_timestamp",
    "entry_price",
    "exit_price",
    "size",
    "pnl",
    "return_pct",
    "direction",
    "side",
    "status",
}

S = 1_000_000_000  # 秒 -> 纳秒

# 引擎 result.trades 形状: 每条是一个已平仓 round-trip
# - entry_price/entry_time_ns: 开仓(取 PositionState.avg_cost)
# - price/timestamp_ns: 平仓
# - realized_pnl: 引擎权威已实现盈亏
# - net_quantity: 负=平多(long), 正=平空(short)
# - quantity: 平仓数量
ENGINE_TRADES = [
    # 做多: 开仓 100 @ t0, 平仓 110 @ t1, pnl=10
    {
        "entry_price": 100.0,
        "entry_time_ns": 1_700_000_000 * S,
        "price": 110.0,
        "timestamp_ns": 1_700_000_060 * S,
        "quantity": 1.0,
        "realized_pnl": 10.0,
        "net_quantity": -1.0,
    },
    # 做多(加仓后 avg_cost): 开仓均价 105.6 @ t2, 平仓 120 @ t3, pnl=36
    {
        "entry_price": 105.6,
        "entry_time_ns": 1_700_000_120 * S,
        "price": 120.0,
        "timestamp_ns": 1_700_000_240 * S,
        "quantity": 2.5,
        "realized_pnl": 36.0,
        "net_quantity": -2.5,
    },
    # 做空: 开仓 100 @ t4, 平仓 99 @ t5, pnl=1
    {
        "entry_price": 100.0,
        "entry_time_ns": 1_700_000_300 * S,
        "price": 99.0,
        "timestamp_ns": 1_700_000_360 * S,
        "quantity": 1.0,
        "realized_pnl": 1.0,
        "net_quantity": 1.0,
    },
]


def test_contract_fields_exact():
    trades = BacktestLoop._format_round_trip_trades(ENGINE_TRADES, "BTCUSDT")
    assert len(trades) == 3
    # 字段集必须与契约完全一致：不允许缺字段，也不允许回流大写兼容字段
    for tr in trades:
        assert set(tr.keys()) == CONTRACT_FIELDS


def test_identity_and_side_semantics():
    trades = BacktestLoop._format_round_trip_trades(ENGINE_TRADES, "BTCUSDT")
    for i, tr in enumerate(trades):
        assert tr["trade_id"] == f"rt-BTCUSDT-{i + 1}"
        assert tr["symbol"] == "BTCUSDT"
        assert tr["status"] == "FILLED"
    # 前两笔 net_quantity<0 → 做多, side=buy(开仓方向)
    assert trades[0]["direction"] == "long"
    assert trades[0]["side"] == "buy"
    assert trades[1]["direction"] == "long"
    assert trades[1]["side"] == "buy"
    # 第三笔 net_quantity>0 → 做空, side=sell
    assert trades[2]["direction"] == "short"
    assert trades[2]["side"] == "sell"


def test_pnl_and_prices_from_engine():
    trades = BacktestLoop._format_round_trip_trades(ENGINE_TRADES, "BTCUSDT")
    # pnl 直接取引擎 realized_pnl, 不再手算
    assert trades[0]["pnl"] == 10.0
    assert trades[0]["entry_price"] == 100.0
    assert trades[0]["exit_price"] == 110.0
    assert trades[0]["size"] == 1.0
    # 加仓后 avg_cost 由引擎算好, QuantCell 不做 FIFO
    assert trades[1]["entry_price"] == 105.6
    assert trades[1]["pnl"] == 36.0
    assert trades[1]["size"] == 2.5
    # 做空 pnl 同样来自引擎
    assert trades[2]["pnl"] == 1.0


def test_timestamps():
    trades = BacktestLoop._format_round_trip_trades(ENGINE_TRADES, "BTCUSDT")
    t0, t2 = trades[0], trades[2]
    # timestamp 是开仓秒级；exit_timestamp 是平仓秒级
    assert t0["timestamp"] == 1_700_000_000
    assert t0["exit_timestamp"] == 1_700_000_060
    assert t0["entry_time"] == "2023-11-14T22:13:20.000Z"
    assert t0["exit_time"] == "2023-11-14T22:14:20.000Z"
    assert t0["formatted_time"] == "2023-11-14 22:13:20"
    assert t2["timestamp"] == 1_700_000_300
    assert t2["exit_timestamp"] == 1_700_000_360


def test_empty_input():
    assert BacktestLoop._format_round_trip_trades([], "BTCUSDT") == []


def test_trade_id_unique_across_symbols():
    # 多品种结果会在 Python 侧聚合 trades,各品种独立编号,trade_id 必须全局唯一
    # (曾因每品种各自 rt-N 撞号导致前端 React duplicate key 报错)
    btc = BacktestLoop._format_round_trip_trades(ENGINE_TRADES, "BTCUSDT")
    ltc = BacktestLoop._format_round_trip_trades(ENGINE_TRADES, "LTCUSDT")
    ids = [tr["trade_id"] for tr in btc + ltc]
    assert len(ids) == len(set(ids))
