"""逐笔对账链路单测：指标卡 fills 计数必须能被「回合内 fill + 悬空 fill」解释。

背景：引擎回传的 fills_detail 此前在映射层被丢弃，落盘始终为空，
详情页"指标卡 4 笔、回合表只展开 2 笔"的缺口无从解释。
"""

from backtest.result_formatter_service import ResultFormatterService


def _fill(fid: int, ts_ns: int, side: str = "Buy", price: float = 100.0, qty: float = 1.0) -> dict:
    return {
        "fill_id": fid,
        "timestamp_ns": ts_ns,
        "instrument": "spot/BTC/USDT",
        "taker_order_id": fid + 1,
        "maker_order_id": fid + 2,
        "taker_side": side,
        "price": price,
        "quantity": qty,
    }


def _rt(fills: list[dict]) -> dict:
    """构造一条 round-trip 记录，fills 为其关联的逐笔（开+平）。"""
    ids = [f["fill_id"] for f in fills]
    return {
        "trade_id": f"rt-BTCUSDT-{ids[0]}",
        "symbol": "BTCUSDT",
        "entry_time": "2026-01-01T00:00:00.000Z",
        "exit_time": "2026-01-01T04:00:00.000Z",
        "entry_price": 100.0,
        "exit_price": 101.0,
        "quantity": 1.0,
        "pnl": 1.0,
        "return_pct": 1.0,
        "fills": fills,
    }


def _run_formatter(results: dict) -> dict:
    formatted = ResultFormatterService.format_axon_results(
        results=results,
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="grid",
    )
    return formatted["BTCUSDT_1h"]


def test_all_fills_matched_no_unclosed():
    """全配对：回合引用了全部 fill → unclosed 为空。"""
    fills = [_fill(0, 1_000_000_000), _fill(1, 2_000_000_000)]
    entry = _run_formatter({"trades": [_rt(fills)], "fills_detail": fills})
    assert entry["unclosed_fills"] == []
    assert entry["fills_detail"] == fills


def test_unclosed_fills_are_leftover():
    """有悬空：4 笔 fill、回合只引用 2 笔 → 悬空 2 笔，加工字段可参展。"""
    fills = [
        _fill(0, 1_000_000_000),
        _fill(1, 2_000_000_000),
        _fill(2, 3_000_000_000, side="Sell", price=102.0, qty=0.5),
        _fill(3, 4_000_000_000, side="Sell", price=98.0, qty=0.25),
    ]
    entry = _run_formatter({"trades": [_rt(fills[:2])], "fills_detail": fills})
    unclosed = entry["unclosed_fills"]
    assert [f["fill_id"] for f in unclosed] == [2, 3]
    f2 = unclosed[0]
    # 悬空只可能是开仓方向；side 归一小写、时间已格式化
    assert f2["side"] == "sell"
    assert f2["offset"] == "open"
    assert f2["price"] == 102.0
    assert f2["formatted_time"]  # 与 rt.fills 展开行同款字段


def test_legacy_result_without_fills_detail():
    """旧数据：无 fills_detail 键 → 两字段皆空，不炸。"""
    entry = _run_formatter({"trades": []})
    assert entry["fills_detail"] == []
    assert entry["unclosed_fills"] == []


def test_rl_prefilled_fill_rows_contract():
    """RL 链的 fills_detail 是预格式化 fill_rows（timestamp 秒 / side 小写 / 自带
    formatted_time），不是 Rust 引擎原始字段。差集计算需兼容该契约，否则悬空
    fill 的时间会退化为 1970、方向为空串（真实踩坑：RL 任务 1353 悬空全 1970）。"""
    prefill = {
        "fill_id": 0,
        "timestamp": 1704067200,  # 秒级
        "formatted_time": "2024-01-01 00:00:00",
        "side": "buy",
        "price": 42475.23,
        "quantity": 0.32,
    }
    entry = _run_formatter({"trades": [], "fills_detail": [prefill]})
    assert entry["unclosed_fills"] == [
        {
            "fill_id": 0,
            "side": "buy",
            "offset": "open",
            "price": 42475.23,
            "quantity": 0.32,
            "timestamp": 1704067200,
            "formatted_time": "2024-01-01 00:00:00",
            "status": "filled",
        }
    ]
