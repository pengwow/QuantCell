"""马丁模板方向语义行为自检。

回测引擎按 target_position 的符号决定多空（正=多 / 负=空），
action_type 只表示「是否更新目标位」。此测试锁定：
做空入场必须输出负 target；加仓在 buy/sell 下才会生效；平仓目标回 0。
"""

from strategy import Action, ActionType, StrategyConfig, StrategyContext
from strategy.templates.martingale import Martingale


def _make_strategy(direction: str) -> Martingale:
    config = StrategyConfig(
        name="martingale",
        symbol="BTCUSDT",
        params={"direction": direction, "base_position": 0.1, "multiplier": 2, "max_multiplier": 4},
    )
    return Martingale(config)


def _bar(close: float) -> dict:
    return {"close": close, "open": close, "high": close, "low": close, "volume": 1.0}


def _feed(strategy: Martingale, closes: list[float]) -> list[Action]:
    ctx = StrategyContext(symbol="BTCUSDT")
    strategy.on_start(ctx)
    return [strategy.on_bar(_bar(c), ctx) for c in closes]


def test_short_direction_opens_with_negative_target():
    """direction=short + 收阴 → 开空：sell + 负 target。"""
    strategy = _make_strategy("short")
    actions = _feed(strategy, [100.0, 99.0])  # 第二根收阴 → 入场

    entry = actions[-1]
    assert entry.action_type == ActionType.Sell
    assert entry.target_position < 0  # 引擎按 target 符号定方向，负=空头


def test_long_direction_opens_with_positive_target():
    """direction=long + 收阳 → 开多：buy + 正 target（对偶用例）。"""
    strategy = _make_strategy("long")
    actions = _feed(strategy, [100.0, 101.0])  # 第二根收阳 → 入场

    entry = actions[-1]
    assert entry.action_type == ActionType.Buy
    assert entry.target_position > 0


def test_short_loss_adds_position_via_sell_with_more_negative_target():
    """空头持仓遇亏损 bar → 加仓：sell + 更负的 target（验证加仓已生效）。"""
    strategy = _make_strategy("short")
    # 收阴入场（entry=99.0），随后收阳对空头是亏损 → 触发加仓
    actions = _feed(strategy, [100.0, 99.0, 100.5])

    add = actions[-1]
    assert add.action_type == ActionType.Sell
    assert add.target_position < 0
    assert add.target_position < actions[1].target_position  # 更负 = 仓位更大


def test_short_profit_closes_with_zero_target():
    """空头持仓遇盈利 bar → 平仓：buy + target=0.0。"""
    strategy = _make_strategy("short")
    # 收阴入场（entry=99.0），随后收跌对空头盈利 → 平仓
    actions = _feed(strategy, [100.0, 99.0, 98.0])

    close = actions[-1]
    assert close.action_type == ActionType.Buy
    assert close.target_position == 0.0
