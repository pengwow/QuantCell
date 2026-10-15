"""strategy.target 仓位换算纯函数测试。"""

from __future__ import annotations

import pytest

from strategy.target import ratio_to_target_qty


def test_ratio_to_qty_basic():
    # 0.1 仓位、10 万权益、价格 5 万 → 目标持有 0.2 个币
    assert ratio_to_target_qty(0.1, 100_000.0, 50_000.0) == pytest.approx(0.2)


def test_ratio_zero_means_flat():
    assert ratio_to_target_qty(0.0, 100_000.0, 50_000.0) == 0.0


def test_ratio_full_position():
    assert ratio_to_target_qty(1.0, 100_000.0, 50_000.0) == pytest.approx(2.0)


def test_negative_ratio_allowed_for_short():
    # 合约做空：负比例 → 负目标数量
    assert ratio_to_target_qty(-0.5, 100_000.0, 50_000.0) == pytest.approx(-1.0)


def test_zero_price_raises():
    with pytest.raises(ValueError, match="price"):
        ratio_to_target_qty(0.1, 100_000.0, 0.0)


def test_negative_equity_raises():
    with pytest.raises(ValueError, match="equity"):
        ratio_to_target_qty(0.1, -1.0, 50_000.0)
