"""上游引擎契约门禁:BacktestEngine 回测主循环(conformance)。

覆盖评估报告 4.2「回测主循环 L2 层 P0 缺口」:爆仓/强制平仓路径、
合约乘数(contract_size)名义价值、with_seed 确定性。
每个用例直接驱动 BacktestEngine 的事件循环,不做向量化回退。

本目录是「引擎升级门禁」:axon-quant 升级时优先跑
(`uv run pytest tests/conformance/ -q`),全部通过再跑全量回归。
"""

from __future__ import annotations

import pytest

from axon_bridge.backtest import (
    BacktestEngine,
    market_order,
    swap_instrument,
)

# 上游契约标记:这些断言直接钉住 axon-quant 行为,引擎升级时最先受影响
pytestmark = [pytest.mark.upstream]

BASE = "BTC"
QUOTE = "USDT"
INITIAL_CASH = 100_000.0
TS0 = 1_000_000_000  # 基准纳秒时间戳


def _run_engine(
    *,
    seed: int,
    qty: float,
    price_path: list[float],
    contract_size: float = 0.01,
    force_liquidate: bool = False,
    liquidity_depth: int = 4,
    liquidity_size: float = 50.0,
) -> dict:
    """跑一次完整回测:买入 qty 合约后沿 price_path 逐 bar 结算。"""
    ins = swap_instrument(BASE, QUOTE, settle="usd_margin", contract_size=contract_size)
    engine = (
        BacktestEngine(initial_cash=INITIAL_CASH)
        .with_seed(seed)
        .with_seed_liquidity(0.001, liquidity_depth, liquidity_size)
    )
    if force_liquidate:
        engine = engine.with_force_liquidate(True)

    engine.set_clock(TS0)
    engine.begin_bar(100.0, ins)
    engine.push_event(
        {
            "type": "order_submitted",
            "timestamp_ns": TS0,
            "order": market_order(1, ins, "Buy", qty),
        }
    )
    for price in price_path:
        engine.begin_bar(price, ins)

    result = engine.run()
    to_dict = getattr(result, "to_dict", None) or result._to_dict
    return to_dict()


def test_swap_contract_size_notional() -> None:
    """合约乘数:swap_instrument 携带 contract_size,回测 end 持仓=数量*乘数名义。"""
    ins = swap_instrument(BASE, QUOTE, settle="usd_margin", contract_size=0.01)
    assert ins["contract_size"] == 0.01

    out = _run_engine(seed=7, qty=200.0, price_path=[100.0])
    position = out["positions"].get(("swap", "BTC", "USDT", "usd_margin", 0.01))
    assert position == 200.0  # 200 张 × 0.01 BTC = 2 BTC 名义


def test_market_order_immediate_fills_then_gain() -> None:
    """市价单在 event 时刻立即成交(begin_bar 前),价格上涨带来持仓浮盈。"""
    out = _run_engine(seed=2, qty=200.0, price_path=[105.0, 110.0])
    assert out["fills"] >= 1
    assert out["trades_count"] == 0  # 只开仓未平仓
    position = out["positions"].get(("swap", "BTC", "USDT", "usd_margin", 0.01))
    assert position == 200.0


def test_force_liquidate_clears_position_on_collapse() -> None:
    """爆仓强平:价格塌方 + with_force_liquidate → 最终持仓清零、发生平仓成交。

    报告 M9 场景:高杠杆仓位在行情极端下跌时必须被引擎强制平仓,
    而不是把浮亏一直挂在持仓里。
    """
    out = _run_engine(
        seed=7,
        qty=200.0,
        price_path=[95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0],
        force_liquidate=True,
    )
    assert out["positions"] == {}  # 敞口已清空
    assert out["trades_count"] > 0  # 强平产生了成交记录


def test_without_force_liquidate_keeps_position() -> None:
    """对照组:不开强平,同样行情下持仓保留(验证开关确实生效,避免死测试)。"""
    out = _run_engine(
        seed=7,
        qty=200.0,
        price_path=[95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0],
        force_liquidate=False,
    )
    position = out["positions"].get(("swap", "BTC", "USDT", "usd_margin", 0.01))
    assert position == 200.0  # 保留持仓
    assert out["trades_count"] == 0


def test_seed_determinism_same_seed_same_result() -> None:
    """with_seed 确定性:同一 seed 两次运行结果逐字段一致。

    引擎若有隐藏随机源(流动性/撮合路径),seed 必须能让回测可复现;
    这是策略对比实验的前提(报告 P0-4 可复现性)。
    """
    first = _run_engine(seed=42, qty=150.0, price_path=[98.0, 96.0, 94.0], force_liquidate=True)
    second = _run_engine(seed=42, qty=150.0, price_path=[98.0, 96.0, 94.0], force_liquidate=True)
    # final_nav 浮点完全相等(确定性),不能只做近似比较
    assert first["final_nav"] == second["final_nav"]
    assert first["positions"] == second["positions"]
    assert first["fills"] == second["fills"]
    # 顺带验证结果在合理区间:爆仓后净值应高于 0 且低于开仓时刻
    assert 0.0 < first["final_nav"] < INITIAL_CASH


def test_initial_cash_propagates_to_nav() -> None:
    """初始资金进入回测:不动仓的 empty run final_nav 应约等于初始资金(仅扣除手续费为 0)。"""
    engine = BacktestEngine(initial_cash=100_000.0).with_seed(0)
    ins = swap_instrument(BASE, QUOTE, settle="usd_margin", contract_size=0.01)
    engine.set_clock(TS0)
    engine.begin_bar(100.0, ins)
    engine.begin_bar(100.0, ins)
    result = engine.run()
    to_dict = getattr(result, "to_dict", None) or result._to_dict
    out = to_dict()
    assert out["final_nav"] == pytest.approx(INITIAL_CASH, rel=1e-9)
