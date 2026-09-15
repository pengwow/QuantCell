"""上游引擎契约门禁:L1MatchingEngine 撮合语义(conformance)。

覆盖评估报告 4.1「撮合层 P0 缺口」:TIF(GTC/IOC/FOK)、部分成交、FIFO 价格-时间优先、
流动性不足、GTC 残单续成交、自成交/重复 id 防护(0.14.2 修复,id 复用边界)。

本目录是「引擎升级门禁」:axon-quant 升级时优先跑(可单独执行
`uv run pytest tests/conformance/ -q`),全部通过再合入并跑全量回归。
"""

from __future__ import annotations

import pytest

from axon_bridge.backtest import L1MatchingEngine, limit_order, market_order, spot_instrument

# 上游契约标记:这些断言直接钉住 axon-quant 行为,引擎升级时最先受影响
pytestmark = [pytest.mark.upstream]

# 撮合面:同价 100.0 对按 1.0 / 100.0 等数量撮合
BASE = "BTC"
QUOTE = "USDT"
PRICE = 100.0


@pytest.fixture
def spot():
    return spot_instrument(BASE, QUOTE)


def test_limit_cross_same_price_fills(spot: dict) -> None:
    """同价 Sell(挂单) + Buy(吃单)→ is_filled=True,remaining=0。"""
    engine = L1MatchingEngine()
    sell = engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    assert sell["is_filled"] is False  # 第一次只是挂单
    assert sell["remaining_quantity"] == 1.0

    buy = engine.submit(limit_order(2, spot, "Buy", PRICE, 1.0))
    assert buy["is_filled"] is True
    assert buy["is_partially_filled"] is False
    assert buy["remaining_quantity"] == 0.0
    assert buy["fills"][0]["quantity"] == 1.0
    assert buy["fills"][0]["price"] == PRICE
    # taker_side 语义: 主动方
    assert buy["fills"][0]["taker_side"] == "BUY"


def test_partial_fill_ioc_taker_side(spot: dict) -> None:
    """IOC 单: 账户只成交一部分,剩余立即撤销(报告 M3 IOC 场景)。"""
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    ioc = engine.submit(limit_order(2, spot, "Buy", PRICE, 2.0, tif="IOC"))
    assert ioc["is_filled"] is False
    assert ioc["is_partially_filled"] is True
    assert ioc["remaining_quantity"] == 1.0  # 未成交部分按 IOC 撤销
    assert len(ioc["fills"]) == 1
    assert ioc["fills"][0]["quantity"] == 1.0


def test_partial_fill_gtc_taker_side(spot: dict) -> None:
    """GTC 单: 大额 Buy 吃小单后,剩余部分继续挂簿(报告 M4 部分成交)。"""
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 100.0))
    gtc = engine.submit(limit_order(2, spot, "Buy", PRICE, 150.0))
    assert gtc["is_filled"] is False
    assert gtc["is_partially_filled"] is True
    assert gtc["remaining_quantity"] == 50.0
    assert gtc["fills"][0]["quantity"] == 100.0


def test_fok_all_or_none(spot: dict) -> None:
    """FOK: 全部可成交才吃,不可全量立即全部不成交(报告 TIF 场景)。"""
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    fok_fail = engine.submit(limit_order(2, spot, "Buy", PRICE, 2.0, tif="FOK"))
    assert fok_fail["is_filled"] is False
    assert fok_fail["remaining_quantity"] == 2.0  # 全撤
    assert fok_fail["fills"] == []

    engine2 = L1MatchingEngine()
    engine2.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    fok_ok = engine2.submit(limit_order(2, spot, "Buy", PRICE, 1.0, tif="FOK"))
    assert fok_ok["is_filled"] is True
    assert fok_ok["remaining_quantity"] == 0.0


def test_market_order_hits_best_ask(spot: dict) -> None:
    """市价单: 直接吃最优卖价(不依赖限价),成交价 = 牌面价。"""
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    mkt = engine.submit(market_order(2, spot, "Buy", 1.0))
    assert mkt["is_filled"] is True
    assert mkt["fills"][0]["price"] == PRICE
    assert mkt["fills"][0]["maker_order_id"] == 1


def test_market_order_on_empty_book(spot: dict) -> None:
    """空簿市价单: 不崩,明确 is_filled=False 并保留未成交数量(报告 M6 流动性不足)。"""
    engine = L1MatchingEngine()
    mkt = engine.submit(market_order(1, spot, "Buy", 1.0))
    assert mkt["is_filled"] is False
    assert mkt["is_partially_filled"] is False
    assert mkt["remaining_quantity"] == 1.0
    assert mkt["fills"] == []


def test_fifo_price_time_priority(spot: dict) -> None:
    """FIFO: 同价位先挂的 Maker 先被吃(报告 M5 价格-时间优先)。"""
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    engine.submit(limit_order(2, spot, "Sell", PRICE, 1.0))

    first = engine.submit(limit_order(3, spot, "Buy", PRICE, 1.0))
    assert first["fills"][0]["maker_order_id"] == 1
    second = engine.submit(limit_order(4, spot, "Buy", PRICE, 1.0))
    assert second["fills"][0]["maker_order_id"] == 2


def test_gtc_resting_quantity_fills_next(spot: dict) -> None:
    """GTC 残量继续挂簿,后续订单继续吃(TC: 部分成交单的连续消费)。"""
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 100.0))
    r1 = engine.submit(limit_order(2, spot, "Buy", PRICE, 40.0))
    assert r1["is_filled"] is True  # taker 全成
    r2 = engine.submit(limit_order(3, spot, "Buy", PRICE, 40.0))
    assert r2["is_filled"] is True
    assert r2["fills"][0]["maker_order_id"] == 1


def test_self_trade_same_order_id_rejected(spot: dict) -> None:
    """自成交防护(报告 M3): 同一订单 id 的 Buy + Sell 不应被撮合。

    0.14.1 实测会自成交(taker_order_id==maker_order_id==7 直接成交);
    axon-quant 0.14.2 已修复,此处为普通回归断言。
    """
    engine = L1MatchingEngine()
    engine.submit(limit_order(7, spot, "Buy", PRICE, 1.0))
    result = engine.submit(limit_order(7, spot, "Sell", PRICE, 1.0))
    # 同 id 挂单仍在簿上,新提交的同 id 卖单必须被拒,不得与自身成交
    assert result["is_filled"] is False
    assert result["fills"] == []


def test_duplicate_order_id_rejected(spot: dict) -> None:
    """订单 id 唯一性: 重复 id 不应被当作独立订单撮合。

    0.14.1 实测重复 id 会直接与上一次订单互为对手盘成交;
    axon-quant 0.14.2 已修复,此处为普通回归断言。
    """
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    result = engine.submit(limit_order(1, spot, "Buy", PRICE, 1.0))
    # 重复 id 被拒:不成交,也不产生对手盘 fill
    assert result["is_filled"] is False
    assert result["fills"] == []


def test_reused_id_after_fill_is_allowed(spot: dict) -> None:
    """id 复用边界: 已成交订单的 id 从活跃簿释放后可复用(与交易所契约一致)。

    该用例同时保护 0.14.2 修复不要过度拦截——防的是「活跃簿内重复」,
    不是「历史 id 永久拉黑」。
    """
    engine = L1MatchingEngine()
    engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    # order 2 吃掉 order 1,双方全部成交离开活跃簿
    filled = engine.submit(limit_order(2, spot, "Buy", PRICE, 1.0))
    assert filled["is_filled"] is True
    # 复用已成交的 id=1: 空簿上挂新卖单,应正常挂单而非被拒
    reused = engine.submit(limit_order(1, spot, "Sell", PRICE, 1.0))
    assert reused["is_filled"] is False
    assert reused["remaining_quantity"] == 1.0
