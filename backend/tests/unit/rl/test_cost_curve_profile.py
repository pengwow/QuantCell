"""P4-1：`CostProfile` × 滑点曲线的接线（曲线优先 / 回落标量 / meta 同源）。

守三件事：
1. 没配曲线时数值与 P2 完全一致（零漂移）；
2. 配了曲线 + 给了名义额时曲线胜出（压过 by_symbol 标量）；
3. 训练 meta 落盘 `cost_profile`（含曲线），回测侧能按名义额读回。
"""

import json

import pandas as pd
import pytest

from services.rl_service import (
    RL_TRANSACTION_COST,
    CostProfile,
    RLService,
    RLTrainConfig,
    transaction_cost_from_meta,
)
from services.slippage import SlippageCurve

CURVE = SlippageCurve(((10_000.0, 2.0), (100_000.0, 10.0)))


def _ohlcv(rows: int = 48) -> pd.DataFrame:
    closes = [100.0] * rows
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [10.0] * rows,
        }
    )


# =============================================================================
# CostProfile：曲线优先 / 回落标量
# =============================================================================


def test_no_curve_keeps_scalar_lookup_zero_drift():
    profile = CostProfile(default=1e-4, by_symbol={"BTCUSDT": 2e-4})
    assert profile.rate_for() == 1e-4
    assert profile.rate_for(symbol="BTCUSDT") == 2e-4
    # 给了 notional 但没曲线 → 仍走标量
    assert profile.rate_for(symbol="BTCUSDT", notional=50_000.0) == 2e-4
    assert profile.kernel_rate(symbol="BTCUSDT") == 2e-4
    assert RLService._cost_rate(RLTrainConfig()) == RL_TRANSACTION_COST


def test_curve_wins_over_scalar_when_notional_given():
    profile = CostProfile(default=1e-4, by_symbol={"BTCUSDT": 2e-4}, slippage_curve=CURVE)
    assert profile.rate_for(symbol="BTCUSDT", notional=10_000.0) == pytest.approx(2e-4)
    assert profile.rate_for(symbol="BTCUSDT", notional=55_000.0) == pytest.approx(6e-4)
    # 没有名义额 → 没有曲线输入，回落标量
    assert profile.rate_for(symbol="BTCUSDT") == 2e-4


def test_kernel_rate_uses_first_tier():
    profile = CostProfile(slippage_curve=CURVE)
    assert profile.kernel_rate() == pytest.approx(2e-4)


def test_curve_rejects_wrong_type():
    with pytest.raises(ValueError, match="slippage_curve 必须是 SlippageCurve"):
        CostProfile(slippage_curve={"tiers": [[1.0, 1.0], [2.0, 2.0]]})  # type: ignore[arg-type]


# =============================================================================
# 序列化 / 配置解析
# =============================================================================


def test_profile_mapping_roundtrip_with_curve():
    profile = CostProfile(default=1e-4, by_symbol={"BTCUSDT": 2e-4}, slippage_curve=CURVE)
    raw = profile.to_mapping()
    assert raw["slippage_curve"] == {"tiers": [[10_000.0, 2.0], [100_000.0, 10.0]]}
    assert CostProfile.from_mapping(raw) == profile


def test_profile_mapping_omits_curve_when_absent():
    assert "slippage_curve" not in CostProfile().to_mapping()


def test_config_parses_curve_from_dict():
    config = RLTrainConfig(
        symbol="BTCUSDT",
        cost_profile={"default": 1e-4, "slippage_curve": {"tiers": [[10_000.0, 2.0], [100_000.0, 10.0]]}},
    )
    assert isinstance(config.cost_profile, CostProfile)
    assert config.cost_profile.slippage_curve == CURVE
    # 训练/内核标量口径 = 曲线首档代表值
    assert RLService._cost_rate(config) == pytest.approx(2e-4)


def test_config_still_rejects_unknown_profile_field():
    with pytest.raises(ValueError, match="未知 cost_profile 字段"):
        RLTrainConfig(cost_profile={"slippage": {}})


# =============================================================================
# meta 回读
# =============================================================================


def test_meta_without_profile_keeps_legacy_scalar():
    assert transaction_cost_from_meta({}) == RL_TRANSACTION_COST
    assert transaction_cost_from_meta({"transaction_cost": 5e-4}) == 5e-4
    # legacy meta 没有 cost_profile → notional 不改变结果
    assert transaction_cost_from_meta({"transaction_cost": 5e-4}, notional=10_000.0) == 5e-4


def test_meta_curve_used_when_notional_given():
    meta = {
        "transaction_cost": 2e-4,
        "cost_profile": {"default": 2e-4, "slippage_curve": CURVE.to_mapping()},
    }
    assert transaction_cost_from_meta(meta, notional=10_000.0) == pytest.approx(2e-4)
    assert transaction_cost_from_meta(meta, notional=55_000.0) == pytest.approx(6e-4)
    # 没有名义额 → 标量（与训练/内核一致）
    assert transaction_cost_from_meta(meta) == pytest.approx(2e-4)


def test_meta_profile_without_curve_stays_scalar():
    meta = {"transaction_cost": 3e-4, "cost_profile": {"default": 3e-4}}
    assert transaction_cost_from_meta(meta, notional=55_000.0) == pytest.approx(3e-4)


def test_meta_corrupt_profile_falls_back_to_scalar():
    meta = {"transaction_cost": 3e-4, "cost_profile": {"tiers": "nope"}}
    assert transaction_cost_from_meta(meta, notional=55_000.0) == pytest.approx(3e-4)


# =============================================================================
# 训练落盘 meta
# =============================================================================


def test_train_writes_curve_into_meta(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    result = svc.train(
        RLTrainConfig(
            data=_ohlcv(),
            total_timesteps=32,
            model_name="meta_curve",
            cost_profile={"default": 1e-4, "slippage_curve": CURVE.to_mapping()},
        )
    )
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["cost_profile"]["slippage_curve"] == CURVE.to_mapping()
    # transaction_cost 记录曲线首档代表值：训练/内核标量同源
    assert meta["transaction_cost"] == pytest.approx(2e-4)
    assert transaction_cost_from_meta(meta, notional=55_000.0) == pytest.approx(6e-4)


def test_train_without_profile_omits_meta_curve(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    result = svc.train(RLTrainConfig(data=_ohlcv(), total_timesteps=32, model_name="meta_no_curve"))
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert "cost_profile" not in meta
    assert meta["transaction_cost"] == RL_TRANSACTION_COST
