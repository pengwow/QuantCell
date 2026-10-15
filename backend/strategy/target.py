"""目标仓位换算纯函数。

回测（BacktestLoop）与实盘（P2 LiveLoop）共用同一套"比例 → 数量"口径，
全系统唯一实现。无 IO、无状态，便于独立单测。
"""

from __future__ import annotations


def ratio_to_target_qty(ratio: float, equity: float, price: float) -> float:
    """目标仓位比例 → 目标持有数量。

    Args:
        ratio: 目标仓位占权益比例，[-1, 1]；负数表示合约做空。
        equity: 账户权益（计价货币，通常是 USDT）。
        price: 当前成交价（base 货币价格）。

    Returns:
        目标持有的 base 货币数量（带符号）。
    """
    if price <= 0:
        raise ValueError(f"price 必须为正数，实际: {price}")
    if equity < 0:
        raise ValueError(f"equity 不能为负，实际: {equity}")
    return ratio * equity / price
