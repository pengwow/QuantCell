"""P2 车道A：reward_terms 配置化 + cost profile 配置化。

守三件事：缺省零漂移、显式配置生效、meta 记录实际生效值。
"""

import json

import pandas as pd
import pytest

from services.rl_service import (
    DEFAULT_REWARD_TERMS,
    REWARD_TERM_KEYS,
    RL_TRANSACTION_COST,
    CostProfile,
    RewardShapingEnv,
    RLService,
    RLTrainConfig,
    transaction_cost_from_meta,
)


def _ohlcv(rows: int = 80, *, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    closes = [start + step * i for i in range(rows)]
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
# 项 1：reward_terms
# =============================================================================


def test_reward_terms_default_matches_legacy_pnl():
    config = RLTrainConfig()
    assert config.reward_terms is None
    assert config.effective_reward_terms() == DEFAULT_REWARD_TERMS
    assert set(config.effective_reward_terms()) == set(REWARD_TERM_KEYS)


def test_reward_terms_partial_override_merges_defaults():
    config = RLTrainConfig(reward_terms={"turnover": -2e-5, "mdd": -1.0})
    assert config.effective_reward_terms() == {**DEFAULT_REWARD_TERMS, "turnover": -2e-5, "mdd": -1.0}


def test_reward_terms_unknown_key_rejected():
    with pytest.raises(ValueError, match="未知 reward term"):
        RLTrainConfig(reward_terms={"pnl": 1.0, "sortino": 0.5})


def test_reward_terms_non_finite_rejected():
    with pytest.raises(ValueError, match="有限数"):
        RLTrainConfig(reward_terms={"pnl": float("nan")})


def test_default_config_env_is_native_and_untouched():
    """缺省不套 shaping：训练环境仍是原生 TradingEnv，reward 数值零漂移。"""
    svc = RLService()
    config = RLTrainConfig(data=_ohlcv())
    env = svc._build_train_env(_ohlcv(), config, cost_rate=RL_TRANSACTION_COST)
    assert not isinstance(env, RewardShapingEnv)
    assert type(env).__name__ == "TradingEnv"


def test_shaping_env_with_pnl_only_tracks_equity_change():
    svc = RLService()
    data = _ohlcv()
    shaped = RewardShapingEnv(svc.create_env(data), {"pnl": 1.0}, cost_rate=RL_TRANSACTION_COST)
    shaped.reset()
    prev = shaped.portfolio_value
    for action in ([0.5], [0.5], [0.0], [1.0]):
        _obs, reward, *_ = shaped.step(action)
        assert reward == pytest.approx(shaped.portfolio_value - prev)
        prev = shaped.portfolio_value


def test_downside_term_only_penalises_losing_steps():
    """加 downside 权重后：亏损步 reward 更低，盈利步不变。"""
    svc = RLService()
    up = RewardShapingEnv(svc.create_env(_ohlcv(step=1.0)), {"pnl": 1.0, "downside": 1.0})
    down = RewardShapingEnv(svc.create_env(_ohlcv(step=-1.0)), {"pnl": 1.0, "downside": 1.0})
    base = RewardShapingEnv(svc.create_env(_ohlcv(step=-1.0)), {"pnl": 1.0})
    up.reset()
    down.reset()
    base.reset()
    up_terms = up.step([0.5])[4]["reward_terms"]
    assert up_terms["downside"] == 0.0  # 盈利步不罚
    down_terms = down.step([0.5])[4]["reward_terms"]
    assert down_terms["downside"] < 0.0
    assert down.step([0.5])[1] < base.step([0.5])[1]


def test_turnover_term_scales_with_traded_notional():
    svc = RLService()
    env = RewardShapingEnv(svc.create_env(_ohlcv(step=0.0)), {"pnl": 0.0, "turnover": 1.0})
    env.reset()
    _, reward, _, _, info = env.step([0.5])
    # 0.5 仓位 × 100 单价 × ~1000 单位 ≈ 50_000 名义额
    assert info["reward_terms"]["turnover"] == pytest.approx(50_000.0, rel=0.01)
    assert reward == pytest.approx(info["reward_terms"]["turnover"])


def test_mdd_term_is_non_negative_current_drawdown():
    svc = RLService()
    up_path = _ohlcv(rows=20, step=0.0)  # 横盘：无回撤
    env = RewardShapingEnv(svc.create_env(up_path), {"pnl": 0.0, "mdd": -1.0})
    env.reset()
    env.step([0.5])
    _, reward, _, _, info = env.step([0.5])
    assert info["reward_terms"]["mdd"] >= 0.0
    assert reward == pytest.approx(-info["reward_terms"]["mdd"])


# =============================================================================
# 项 2：cost profile
# =============================================================================


def test_cost_profile_default_equals_constant():
    profile = CostProfile()
    assert profile.rate_for(symbol="BTCUSDT") == RL_TRANSACTION_COST
    assert profile.rate_for(symbol="ETHUSDT", candle_type="swap") == RL_TRANSACTION_COST
    # config 不传 profile → 训练费率仍是常量
    assert RLService._cost_rate(RLTrainConfig()) == RL_TRANSACTION_COST


def test_cost_profile_lookup_precedence():
    profile = CostProfile(
        default=1e-4,
        by_symbol={"BTCUSDT": 2e-4},
        by_candle_type={"swap": 5e-4},
    )
    assert profile.rate_for(symbol="BTCUSDT", candle_type="swap") == 2e-4  # 交易对优先
    assert profile.rate_for(symbol="BTCUSDT".lower(), candle_type="spot") == 2e-4  # 大小写归一
    assert profile.rate_for(symbol="ETHUSDT", candle_type="swap") == 5e-4
    assert profile.rate_for(symbol="ETHUSDT", candle_type="spot") == 1e-4


def test_cost_profile_from_mapping_and_validation():
    config = RLTrainConfig(
        symbol="BTCUSDT",
        candle_type="swap",
        cost_profile={"default": 1e-4, "by_symbol": {"BTCUSDT": 3e-4}},
    )
    assert isinstance(config.cost_profile, CostProfile)
    assert RLService._cost_rate(config) == 3e-4

    with pytest.raises(ValueError, match="未知 cost_profile 字段"):
        RLTrainConfig(cost_profile={"by_symbols": {}})
    with pytest.raises(ValueError, match="有限非负数"):
        CostProfile(default=-1e-4)


def test_cost_profile_rate_reaches_training_env():
    """profile 费率必须真的进训练环境：同动作下手续费按比例放大。"""
    svc = RLService()
    data = _ohlcv(rows=30, step=0.0)
    cheap = svc.create_env(data, transaction_cost=RL_TRANSACTION_COST)
    dear = svc.create_env(data, transaction_cost=RL_TRANSACTION_COST * 10)
    for env in (cheap, dear):
        env.reset()
        env.step([0.5])
    ratio = dear.info["transaction_costs"] / cheap.info["transaction_costs"]
    assert ratio == pytest.approx(10.0, rel=1e-6)


def test_transaction_cost_from_meta_falls_back_for_legacy_meta():
    assert transaction_cost_from_meta({}) == RL_TRANSACTION_COST
    assert transaction_cost_from_meta({"reward_type": "pnl"}) == RL_TRANSACTION_COST
    assert transaction_cost_from_meta({"transaction_cost": 5e-4}) == 5e-4
    assert transaction_cost_from_meta({"transaction_cost": -1.0}) == RL_TRANSACTION_COST


# =============================================================================
# 训练完成 meta
# =============================================================================


def test_train_writes_reward_terms_and_cost_into_meta(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    result = svc.train(
        RLTrainConfig(
            data=_ohlcv(rows=48),
            total_timesteps=32,
            model_name="meta_terms",
            reward_terms={"turnover": -1e-6},
            cost_profile={"default": 2e-4},
        )
    )
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["reward_terms"] == {**DEFAULT_REWARD_TERMS, "turnover": -1e-6}
    assert set(meta["reward_terms"]) == set(REWARD_TERM_KEYS)
    assert meta["transaction_cost"] == 2e-4
    # OOS key 归另一车道，本车道不动
    assert "oos" not in meta


def test_default_train_meta_records_pnl_only_terms(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    result = svc.train(RLTrainConfig(data=_ohlcv(rows=48), total_timesteps=32, model_name="meta_default"))
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["reward_terms"] == DEFAULT_REWARD_TERMS
    assert meta["transaction_cost"] == RL_TRANSACTION_COST
