"""P4-1：量分档成本曲线（`services.slippage`）的纯函数面。

只测曲线机制本身：校验、插值、钳制、序列化、标定。
与 `CostProfile` 的接线在 `tests/unit/rl/test_cost_curve_profile.py`。
"""

import numpy as np
import pytest

from services.slippage import (
    SlippageCurve,
    calibrate_curve,
    relative_spread_bps,
)

BASIC = ((10_000.0, 2.0), (100_000.0, 10.0))


# =============================================================================
# 校验
# =============================================================================


def test_curve_requires_two_tiers():
    with pytest.raises(ValueError, match="至少需要 2 档"):
        SlippageCurve(((10_000.0, 2.0),))


def test_curve_rejects_non_increasing_notional():
    with pytest.raises(ValueError, match="严格递增"):
        SlippageCurve(((100_000.0, 2.0), (100_000.0, 3.0)))


@pytest.mark.parametrize("bps", [-0.1, float("nan"), float("inf")])
def test_curve_rejects_bad_cost(bps):
    with pytest.raises(ValueError, match="成本必须是有限非负数"):
        SlippageCurve(((10_000.0, 2.0), (100_000.0, bps)))


@pytest.mark.parametrize("notional", [-1.0, float("inf")])
def test_curve_rejects_bad_notional(notional):
    with pytest.raises(ValueError, match="名义额档位必须是有限非负数"):
        SlippageCurve(((notional, 2.0), (100_000.0, 3.0)))


# =============================================================================
# 插值 / 钳制
# =============================================================================


def test_cost_hits_tiers_exactly():
    curve = SlippageCurve(BASIC)
    assert curve.cost_bps(10_000.0) == pytest.approx(2.0)
    assert curve.cost_bps(100_000.0) == pytest.approx(10.0)


def test_cost_interpolates_between_tiers():
    curve = SlippageCurve(BASIC)
    # 中点 = 成本中点（折线线性）
    assert curve.cost_bps(55_000.0) == pytest.approx(6.0)
    # 1/4 处
    assert curve.cost_bps(32_500.0) == pytest.approx(4.0)


def test_cost_clamps_at_both_ends():
    curve = SlippageCurve(BASIC)
    assert curve.cost_bps(0.0) == pytest.approx(2.0)
    assert curve.cost_bps(10_000_000.0) == pytest.approx(10.0)


def test_cost_rate_converts_bps_to_fraction():
    curve = SlippageCurve(((1_000.0, 5.0), (2_000.0, 5.0)))
    assert curve.cost_rate(1_500.0) == pytest.approx(5e-4)
    assert curve.representative_rate() == pytest.approx(5e-4)


def test_representative_rate_is_first_tier():
    curve = SlippageCurve(BASIC)
    assert curve.representative_rate() == pytest.approx(2.0 * 1e-4)


def test_cost_bps_rejects_negative_notional():
    with pytest.raises(ValueError, match="名义成交额必须是有限非负数"):
        SlippageCurve(BASIC).cost_bps(-1.0)


# =============================================================================
# 序列化
# =============================================================================


def test_mapping_roundtrip():
    curve = SlippageCurve(BASIC)
    raw = curve.to_mapping()
    assert raw == {"tiers": [[10_000.0, 2.0], [100_000.0, 10.0]]}
    assert SlippageCurve.from_mapping(raw) == curve


def test_from_mapping_rejects_unknown_field():
    with pytest.raises(ValueError, match="未知 slippage_curve 字段"):
        SlippageCurve.from_mapping({"tiers": [[1.0, 1.0], [2.0, 2.0]], "quantiles": [0.5]})


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"tiers": [[1.0, 1.0], [2.0]]},
        {"tiers": [[1.0, "x"], [2.0, 2.0]]},
    ],
)
def test_from_mapping_rejects_malformed_tiers(raw):
    with pytest.raises(ValueError, match="slippage_curve"):
        SlippageCurve.from_mapping(raw)


# =============================================================================
# 标定
# =============================================================================


def test_calibrate_maps_quantiles_to_tiers():
    # 100 个 1..100 bps 的观测，分位点可精确预期
    obs = np.arange(1.0, 101.0)
    curve = calibrate_curve(
        obs,
        notional_tiers=(1_000.0, 10_000.0, 100_000.0),
        quantiles=(0.5, 0.9, 0.99),
        buffer_bps=1.0,
        fee_bps=0.5,
    )
    q = np.quantile(obs, [0.5, 0.9, 0.99])
    expected = [float(s) / 2.0 + 1.0 + 0.5 for s in q]
    assert curve.notionals == (1_000.0, 10_000.0, 100_000.0)
    assert list(curve.costs_bps) == pytest.approx(expected)
    # 分位点递增 → 成本递增（曲线才单调）
    assert curve.costs_bps[0] < curve.costs_bps[1] < curve.costs_bps[2]


def test_calibrate_converts_absolute_spread_with_mid_price():
    curve = calibrate_curve([0.2, 0.2, 0.2], mid_price=100.0, buffer_bps=0.0, fee_bps=0.0)
    # 0.2 / 100 * 1e4 = 20 bps → 成本 = 半价差 = 10 bps
    assert list(curve.costs_bps) == pytest.approx([10.0, 10.0, 10.0])


def test_calibrate_drops_non_finite_and_negative_observations():
    curve = calibrate_curve([np.nan, -1.0, np.inf, 2.0, 2.0], buffer_bps=0.0)
    assert list(curve.costs_bps) == pytest.approx([1.0, 1.0, 1.0])


def test_calibrate_rejects_empty_observations():
    with pytest.raises(ValueError, match="spread 观测为空"):
        calibrate_curve([np.nan, -1.0])


def test_calibrate_rejects_tier_quantile_length_mismatch():
    with pytest.raises(ValueError, match="数量必须一致"):
        calibrate_curve([1.0, 2.0], notional_tiers=(1_000.0,), quantiles=(0.5, 0.9))


@pytest.mark.parametrize("quantile", [0.0, 1.0, -0.1])
def test_calibrate_rejects_bad_quantile(quantile):
    with pytest.raises(ValueError, match="分位点必须落在"):
        calibrate_curve([1.0, 2.0], notional_tiers=(1_000.0, 2_000.0), quantiles=(quantile, 0.9))


def test_calibrate_rejects_bad_buffer_and_fee():
    with pytest.raises(ValueError, match="buffer_bps / fee_bps"):
        calibrate_curve([1.0, 2.0], buffer_bps=-1.0)
    with pytest.raises(ValueError, match="buffer_bps / fee_bps"):
        calibrate_curve([1.0, 2.0], fee_bps=float("nan"))


def test_calibrate_rejects_bad_mid_price():
    with pytest.raises(ValueError, match="mid_price 必须是有限正数"):
        calibrate_curve([1.0, 2.0], mid_price=0.0)


# =============================================================================
# 绝对价差 → bps
# =============================================================================


def test_relative_spread_bps_scalar_and_series_mid():
    assert relative_spread_bps([0.2, 0.02], 100.0) == pytest.approx([20.0, 2.0])
    assert relative_spread_bps([0.2, 0.2], [100.0, 200.0]) == pytest.approx([20.0, 10.0])
