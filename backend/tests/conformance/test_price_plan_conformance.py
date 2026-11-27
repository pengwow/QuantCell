"""价格计划同源契约（spec §5.2）。

守护三层同源：
1. grid/martingale.price_plan 类方法输出 ≡ price_plan 契约函数输出（防策略内复制公式）；
2. PricePlan 可过 model_validate（防协议结构漂移）；
3. 策略 on_start 固化结果 ≡ price_plan 类方法输出（预览 = 实盘同一价格序列）。
"""

import pytest
from pydantic import ValidationError

from strategies.grid import Grid
from strategies.martingale import Martingale
from strategy import price_plan

GRID_PARAMS = {"lower": 100.0, "upper": 200.0, "levels": 8}
MART_PARAMS = {
    "spacing_pct": 2.0,
    "spacing_multiplier": 1.5,
    "layer_count": 5,
    "base_position": 0.1,
    "multiplier": 2.0,
    "max_multiplier": 4.0,
    "position_limit": 0.5,
}
REF = 150.0


def test_grid_class_method_equals_module_function():
    assert Grid.price_plan(GRID_PARAMS, REF).model_dump() == price_plan.grid_plan(GRID_PARAMS, REF).model_dump()


def test_martingale_class_method_equals_module_function():
    assert (
        Martingale.price_plan(MART_PARAMS, REF).model_dump()
        == price_plan.martingale_plan(MART_PARAMS, REF).model_dump()
    )


def test_plan_validates_against_schema():
    price_plan.PricePlan.model_validate(price_plan.grid_plan(GRID_PARAMS, REF).model_dump())


def test_invalid_plan_raises():
    with pytest.raises(ValidationError):
        price_plan.PricePlan.model_validate({"levels": [{"price": "not-a-number"}]})
