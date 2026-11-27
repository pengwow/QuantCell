"""price_plan 纯函数单测 — 公式黄金用例（spec §5.1）。"""

import pytest

from strategy.price_plan import grid_plan, martingale_plan


class TestGridPlan:
    def test_equal_spacing_lines_and_targets(self):
        # 4 档 → 5 条线（demo 定稿 n+1 条），低档买/高档卖/中枢 mid
        plan = grid_plan({"lower": 100.0, "upper": 200.0, "levels": 4, "position_limit": 0.1}, ref_price=150.0)
        assert [lv.price for lv in plan.levels] == [100.0, 125.0, 150.0, 175.0, 200.0]
        # target_i = -(i - levels/2)/(levels/2) * limit → 低档为正=买
        assert plan.levels[0].action == "buy" and plan.levels[0].target_position == pytest.approx(0.1)
        assert plan.levels[2].action == "mid" and plan.levels[2].target_position == 0.0
        assert plan.levels[4].action == "sell" and plan.levels[4].target_position == pytest.approx(-0.1)
        assert plan.summary.price_min == 100.0 and plan.summary.price_max == 200.0
        assert plan.summary.entry_price == 150.0
        assert plan.warnings == []

    def test_ref_out_of_range_warns(self):
        plan = grid_plan({"lower": 100.0, "upper": 200.0, "levels": 4, "position_limit": 0.1}, ref_price=300.0)
        assert plan.warnings and "区间外" in plan.warnings[0]

    def test_invalid_params_warns(self):
        plan = grid_plan({"lower": 200.0, "upper": 100.0, "levels": 4, "position_limit": 0.1}, ref_price=150.0)
        assert plan.warnings  # upper<=lower 不抛异常，出 warning


class TestMartingalePlan:
    PARAMS = {
        "spacing_pct": 2.0,
        "spacing_multiplier": 1.5,
        "layer_count": 5,
        "base_position": 0.1,
        "multiplier": 2.0,
        "max_multiplier": 4.0,
        "position_limit": 0.5,
        "take_profit_pct": 1.0,
    }

    def test_layer_prices_and_positions(self):
        plan = martingale_plan(self.PARAMS, ref_price=100.0)
        buys = [lv for lv in plan.levels if lv.action == "buy"]
        assert len(buys) == 5  # 建仓 + 4 加仓层
        assert buys[0].price == pytest.approx(100.0)  # 建仓=ref
        assert buys[1].price == pytest.approx(100.0 * (1 - 0.02))  # 层1
        assert buys[2].price == pytest.approx(100.0 * (1 - 0.02 - 0.03))  # 累加式 dip
        assert buys[4].price == pytest.approx(100.0 * (1 - 0.02 - 0.03 - 0.045 - 0.0675))
        assert buys[0].target_position == pytest.approx(0.5 * 0.1 * 1.0)  # limit*base*mult^0
        assert buys[2].target_position == pytest.approx(0.5 * 0.1 * 2.0)
        assert buys[4].target_position == pytest.approx(0.5 * 0.1 * 4.0)  # mult^4 截断到 max=4
        tps = [lv for lv in plan.levels if lv.action == "tp"]
        assert len(tps) == 1
        # 篮子均价 = Σ(p*pos)/Σpos；止盈 = avg*(1+tp%/100)
        prices = [b.price for b in buys]
        poss = [b.target_position for b in buys]
        avg = sum(p * q for p, q in zip(prices, poss, strict=True)) / sum(poss)
        assert tps[0].price == pytest.approx(avg * 1.01)

    def test_full_exposure_warning(self):
        plan = martingale_plan(dict(self.PARAMS, position_limit=1.0, base_position=0.3), ref_price=100.0)
        # 满 层 = 1.0*0.3*15 = 4.5 → 远超 position_limit=1.0
        assert any("满层" in w for w in plan.warnings)

    def test_layers_one_boundary(self):
        plan = martingale_plan(dict(self.PARAMS, layer_count=1), ref_price=100.0)
        assert [lv.action for lv in plan.levels] == ["buy", "tp"]

    def test_spacing_overflow_warns(self):
        # dip 累计 ≥ 100% → 层价非正，必须红牌而非崩溃
        plan = martingale_plan(
            dict(self.PARAMS, spacing_pct=60.0, spacing_multiplier=2.0, layer_count=4), ref_price=100.0
        )
        assert any("非正" in w or "过大" in w for w in plan.warnings)
