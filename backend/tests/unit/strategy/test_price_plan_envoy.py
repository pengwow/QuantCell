"""策略 price_plan 协议与执行器语义测试（spec §5.1/5.2）。

同源契约 monkeypatch 法：篡改 price_plan 输出 → 策略 on_bar 固化结果随之变化
即证明策略确实消费 price_plan（防止复制公式绕过）。
"""

import pytest

from strategies.grid import Grid
from strategies.martingale import Martingale
from strategy import ActionType
from strategy.base import StrategyConfig
from strategy.price_plan import PricePlan, PricePlanLevel, PricePlanSummary


def _cfg(name, **params):
    return StrategyConfig(name=name, symbol="BTCUSDT", position_limit=0.1, params=params)


def _bar(close, **_ignored):
    # 执行器只消费 close（grid）或 close/open（martingale both 方向）
    return {"close": close}


def _run_grid_and_expose_plan():
    s = Grid(_cfg("grid", lower=100.0, upper=200.0, levels=4))
    s.on_start(None)
    # 时序：on_start 只做复位，首根 on_bar 才用其 close 固化计划（与 worker 启动预览同口径）
    s.on_bar(_bar(150.0), None)
    # 同源：执行器固化结果与 price_plan() 输出逐字段一致（同一公式）
    expected = Grid.price_plan({"lower": 100.0, "upper": 200.0, "levels": 4, "position_limit": 0.1}, ref_price=150.0)
    assert s._plan.levels == expected.levels
    return s


def test_grid_plan_fixed_on_start():
    s = _run_grid_and_expose_plan()
    # 出界 → hold（自适应已删除：upper 不得再被改成 close*1.05）
    act = s.on_bar(_bar(300.0), None)
    assert act.action_type == ActionType.Hold
    assert s._plan.levels[0].price == 100.0  # 区间未被自适应改写


def test_grid_cross_level_triggers_action():
    s = _run_grid_and_expose_plan()
    # helper 里首根 bar(150) 已按中枢定档；此后穿层才触发
    act = s.on_bar(_bar(120.0), None)  # 跌至中枢下一侧 → buy
    assert act.action_type == ActionType.Buy
    act2 = s.on_bar(_bar(180.0), None)  # 升至高位档 → sell
    assert act2.action_type == ActionType.Sell


def test_martingale_layered_add_on():
    s = Martingale(
        _cfg(
            "martingale",
            direction="long",
            base_position=0.1,
            multiplier=2.0,
            max_multiplier=4.0,
            position_limit=0.5,
            spacing_pct=2.0,
            spacing_multiplier=1.5,
            layer_count=5,
            take_profit_pct=1.0,
        )
    )
    s.on_start(None)
    # 时序（spec 固化协议）：首根 on_bar 按 close=100 固化计划并开建仓层；
    # 加仓层从第二根 bar 起才可能触发。
    # 层价按 dip 累加公式 = 100/98/95/90.5/83.75（黄金用例以 test_price_plan 为准）
    act = s.on_bar(_bar(100.0), None)
    assert act.action_type == ActionType.Buy  # 建仓层开仓
    # 直接下探到最深层价以下 → 触发第 4 加仓层
    # （目标 = limit*base*min(multiplier^3, max_multiplier) = 0.5*0.1*4 = 0.2）
    act2 = s.on_bar(_bar(83.5), None)
    assert act2.action_type == ActionType.Hold
    assert act2.target_position == pytest.approx(0.2)


def test_martingale_monkeypatch_breaks_plan(monkeypatch):
    """同源契约：篡改 price_plan 输出，on_bar 固化随之被污染。"""

    def fake(params, ref):
        return PricePlan(
            levels=[PricePlanLevel(index=0, price=1.0, action="buy", target_position=1.0, label="X")],
            summary=PricePlanSummary(price_min=1.0, price_max=1.0, entry_price=ref),
            warnings=[],
        )

    monkeypatch.setattr(Martingale, "price_plan", staticmethod(fake))
    s = Martingale(_cfg("martingale", direction="long", base_position=0.1, spacing_pct=2.0))
    s.on_start(None)
    s.on_bar(_bar(100.0), None)  # 首根 bar 固化（走 price_plan 类方法）
    assert [lv.price for lv in s._plan.levels] == [1.0]  # 策略确实消费了 price_plan 输出
