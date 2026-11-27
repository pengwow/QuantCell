"""马丁格尔模板分层语义测试（2026-11 计划型语义重写）。

旧语义「每根亏损 bar 倍数翻倍」已随模板升级移除；新语义：价格每跌一层
间距触发一层加仓（long 向下 / short 向上镜像），篮子止盈后整套重置。
公式权威 = strategy.price_plan.martingale_plan（模板与创建版策略共用）；
「固化=预览」同源契约由 test_price_plan_envoy.py 守护，本文件锁定
方向符号语义与层执行行为。
"""

import pytest

from strategy import ActionType
from strategy.base import StrategyConfig
from strategy.templates.martingale import Martingale


def _cfg(**params) -> StrategyConfig:
    base = {
        "direction": "long",
        "spacing_pct": 2.0,
        "spacing_multiplier": 1.5,
        "layer_count": 3,
        "take_profit_pct": 1.0,
    }
    base.update(params)
    return StrategyConfig(name="martingale", symbol="BTCUSDT", position_limit=1.0, params=base)


def _bar(close: float, **extra) -> dict:
    # both 方向的阴阳判定需要 open
    d = {"close": close}
    d.update(extra)
    return d


def test_long_direction_opens_with_positive_target():
    s = Martingale(_cfg(direction="long", base_position=0.1))
    # 时序（固化协议）：首根 on_bar 按本根 close 固化计划并立即开建仓层
    act = s.on_bar(_bar(100.0), None)
    assert act.action_type == ActionType.Buy
    # 正 target = 多头方向（引擎按 target 符号定多空）
    assert act.target_position > 0


def test_short_direction_opens_with_negative_target():
    s = Martingale(_cfg(direction="short", base_position=0.1))
    act = s.on_bar(_bar(100.0), None)
    # 做空必须用负 target + sell（buy/sell 只表方向启动，不决定多空）
    assert act.action_type == ActionType.Sell
    assert act.target_position < 0


def test_both_direction_by_bar_direction():
    s = Martingale(_cfg(direction="both", base_position=0.1))
    yang = s.on_bar(_bar(101.0, open=100.0), None)  # 阳线 → 多
    assert yang.action_type == ActionType.Buy and yang.target_position > 0

    s2 = Martingale(_cfg(direction="both", base_position=0.1))
    yin = s2.on_bar(_bar(99.0, open=100.0), None)  # 阴线 → 空
    assert yin.action_type == ActionType.Sell and yin.target_position < 0


def test_long_dip_triggers_next_layer():
    """公式口径：pos_k = limit×base×mult^(k−1)——第 1 加仓层仓位不变，第 2 层起 ×multiplier。"""
    s = Martingale(_cfg(direction="long", base_position=0.1, multiplier=2.0, max_multiplier=4.0))
    s.on_bar(_bar(100.0), None)
    # 未触及首层触发价（100×(1−2%)=98）→ hold 保持建仓层目标
    hold = s.on_bar(_bar(99.9), None)
    assert hold.action_type == ActionType.Hold
    assert hold.target_position == pytest.approx(0.1)
    # 跌破 98 → 触发第 1 加仓层（mult^0=1，仓位不变）
    add1 = s.on_bar(_bar(97.0), None)
    assert add1.action_type == ActionType.Hold
    assert add1.target_position == pytest.approx(0.1)
    # 继续跌破第 2 层触发价（100×(1−2%−2%×1.5)=95）→ 仓位 ×multiplier
    add2 = s.on_bar(_bar(94.0), None)
    assert add2.action_type == ActionType.Hold
    assert add2.target_position == pytest.approx(0.2)


def test_basket_take_profit_closes_and_resets():
    """篮子止盈按已触发层动态均价触发：摊平后反弹才止盈；平仓整套重置。

    2026-11-27 修复背景：旧实现用「计划全层均价」固定触发价（低于建仓价），
    建仓后小幅回调即在亏损位误触发止盈；新口径 tp = 已触发篮子均价 × (1+tp%)。
    """
    s = Martingale(_cfg(direction="long", base_position=0.1, multiplier=2.0))
    s.on_bar(_bar(100.0), None)  # 建仓 100 → 单层篮子 tp = 101
    assert s.on_bar(_bar(100.5), None).action_type == ActionType.Hold  # 未及 101 不止盈
    s.on_bar(_bar(97.0), None)  # 触发第 2 层加仓 → 篮子均价 (100×0.1+98×0.2)/0.3 ≈ 98.67 → tp ≈ 99.65
    act = s.on_bar(_bar(101.0), None)  # 反弹越过动态 tp → 全平
    assert act.action_type == ActionType.Sell
    assert act.target_position == 0.0
    # 整套重置：下一根 bar 重新固化新一轮计划
    assert s._pos_dir == 0
    assert s._plan is None
