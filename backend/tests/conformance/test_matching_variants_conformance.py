"""上游引擎契约门禁:撮合变体 —— 暗池 / 拍卖 / 跨对 / 市场冲击(conformance)。

覆盖评估报告 4.1 M8(暗池/拍卖/跨对)与 M9(冲击成本)P2 缺口。
axon-quant 升级时最先受影响的撮合行为契约。

升级门禁:`uv run pytest tests/conformance/ -q` 先行全绿,再跑全量回归。
"""

from __future__ import annotations

import pytest

from axon_bridge.backtest import (
    ImpactedMatchingEngine,
    ImpactedMatchingEngineBuilder,
    market_order,
    spot_instrument,
    swap_instrument,
)

# 上游契约标记:断言钉住 axon-quant 行为,引擎升级时最先受影响
pytestmark = [pytest.mark.upstream]


# ═══════════════════════════════════════════════════════════════
# M8: 暗池 / 拍卖 / 跨对(MultiAssetMatchingEngine)
# ═══════════════════════════════════════════════════════════════


def test_auction_clearing_price_fills_crossed_book() -> None:
    """拍卖模式:穿价簿清算 → 清算价落在买卖交叉区间,产生成交。

    Buy 102×5 / Buy 100×2 挂簿,Sell 98×3 吃入 → 撮合价应为 maker 价(102),
    未成交单(剩余 Buy)保留计数。
    """
    from axon_quant import MultiAssetMatchingEngine

    from axon_bridge.backtest import limit_order

    btc = spot_instrument("BTC", "USDT")
    engine = MultiAssetMatchingEngine()
    engine.register_instrument(btc)
    engine.set_batch_mode("Auction")
    assert engine.batch_mode == "auction"

    engine.submit(limit_order(1, btc, "Buy", 102.0, 5.0))
    engine.submit(limit_order(2, btc, "Sell", 98.0, 3.0))
    engine.submit(limit_order(3, btc, "Buy", 100.0, 2.0))

    result = engine.run_auction(btc)
    # 清算价在 [98, 102] 交叉区间内
    assert 98.0 <= result.clearing_price <= 102.0
    assert result.clearing_volume > 0
    assert result.has_trades() is True
    assert len(result.fills) >= 1
    # 拍卖语义:成交价 = 清算价;taker sell 吃 maker buy
    fill = result.fills[0]
    assert fill["taker_order_id"] == 2 and fill["maker_order_id"] == 1
    assert fill["price"] == result.clearing_price
    assert fill["quantity"] == 3.0
    # Sell 3 全部成交后,剩余未成交挂单 > 0
    assert result.unfilled_order_count >= 1


def test_dark_pool_hidden_orders_match() -> None:
    """暗池模式:完全隐藏单(hidden>0, visible=0)双方互吃 → 在暗池簿内成交。

    0.14.2 起同 id 防护同样约束暗池,订单 id 需互不相同。
    """
    from axon_quant import DarkOrder, MultiAssetMatchingEngine

    engine = MultiAssetMatchingEngine()
    btc = spot_instrument("BTC", "USDT")
    engine.register_instrument(btc)
    engine.set_batch_mode("DarkPool")

    def dark(order_id: int, side: str) -> DarkOrder:
        return DarkOrder(
            order_id=order_id,
            kind="spot",
            base="BTC",
            quote="USDT",
            side=side,
            price=100.0,
            quantity=5.0,
            hidden_quantity=5.0,
            visible_quantity=0.0,
            order_type="limit",
            tif="GTC",
        )

    engine.submit_dark_order(dark(10, "Buy"))
    fills = engine.submit_dark_order(dark(11, "Sell"))
    assert len(fills) == 1
    assert fills[0]["taker_order_id"] == 11
    assert fills[0]["maker_order_id"] == 10
    assert fills[0]["price"] == 100.0
    assert fills[0]["quantity"] == 5.0


def test_cross_pair_arbitrage_detection() -> None:
    """跨对套利:注册 spot+swap 跨对后,detect_arbitrage 对每个 CrossPair 返回机会。"""
    from axon_quant import CrossPair, MultiAssetMatchingEngine

    engine = MultiAssetMatchingEngine()
    btc = spot_instrument("BTC", "USDT")
    swap = swap_instrument("BTC", "USDT", "usd_margin", 0.01)
    engine.register_instrument(btc)
    engine.register_instrument(swap)

    cp = CrossPair(
        leg1={"kind": "spot", "base": "BTC", "quote": "USDT"},
        leg2={"kind": "swap", "base": "BTC", "quote": "USDT", "settle": "usd_margin", "contract_size": 0.01},
        ratio=1.0,
        max_quantity=100.0,
    )
    engine.register_cross_pair(cp)
    assert engine.cross_pair_count == 1

    opportunities = engine.detect_arbitrage()
    assert len(opportunities) == 1
    opp = opportunities[0]
    # 无价差时无套利空间,但对象与跨对元数据完整
    assert opp.estimated_profit == 0.0
    assert opp.deviation == 0.0


# ═══════════════════════════════════════════════════════════════
# M9: 冲击成本模型(ImpactedMatchingEngine)
# ═══════════════════════════════════════════════════════════════


def _avg_fill_price(result: dict) -> float:
    """成交量加权平均成交价;无成交时抛断言错误。"""
    fills = result["fills"]
    assert fills, "期望至少一笔成交"
    return sum(f["price"] * f["quantity"] for f in fills) / sum(f["quantity"] for f in fills)


def test_impact_engine_direct_cross_applies_slippage() -> None:
    """冲击引擎对敲成交价 > 裸成交价:BUY 方向叠加正向即时冲击。"""
    from axon_bridge.backtest import limit_order

    btc = spot_instrument("BTC", "USDT")
    engine = ImpactedMatchingEngine("linear", 0.05)
    engine.submit(limit_order(1, btc, "Sell", 100.0, 5.0))
    result = engine.submit(limit_order(2, btc, "Buy", 100.0, 5.0))

    assert result["is_filled"] is True
    # 冲击模型将 BUY 成交价从 100.0 上调(滑点方向正确)
    assert _avg_fill_price(result) > 100.0


def test_impact_engine_bigger_order_pays_more_slippage() -> None:
    """播种流动性后:大单成交量加权均价 > 小单(冲击随单量单调上升)。"""
    btc = spot_instrument("BTC", "USDT")
    engine = ImpactedMatchingEngine("linear", 0.05)
    # seed_liquidity 返回更新后的订单 id 计数器,后续订单必须从该值起编号,
    # 否则撞上 0.14.2 重复 id 拒单(seeded 单占用 id 1..N)
    next_id = engine.seed_liquidity(100.0, 0.5, 5, 50.0, btc, 1)

    small = engine.submit(market_order(next_id, btc, "Buy", 10.0))
    big = engine.submit(market_order(next_id + 1, btc, "Buy", 120.0))

    assert _avg_fill_price(big) > _avg_fill_price(small)
    # 大单吃穿多层深度
    assert len(big["fills"]) > 1
    # 永久冲击偏移累计 > 0,且可重置
    assert engine.permanent_offset() > 0.0
    engine.reset_impact_state()
    assert engine.permanent_offset() == 0.0


def test_impact_engine_builder_power_law() -> None:
    """Builder 链式构造 power_law 冲击模型,行为与 linear 同契约。"""
    btc = spot_instrument("BTC", "USDT")
    engine = (
        ImpactedMatchingEngineBuilder().model_type("power_law").coefficient(0.1).exponent(0.5).depth_levels(5).build()
    )
    assert engine.model_name() == "PowerLawImpact"

    next_id = engine.seed_liquidity(100.0, 0.5, 5, 50.0, btc, 1)
    result = engine.submit(market_order(next_id, btc, "Buy", 100.0))
    assert result["is_filled"] is True
    assert _avg_fill_price(result) > 100.5  # 高于最优 ask(100.5)
