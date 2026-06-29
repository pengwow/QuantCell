"""Tests for services/rl_service.py — RLService."""

import pandas as pd
import pytest

try:
    from axon_quant.rl import TradingEnv
    RL_AVAILABLE = True
except ImportError:
    RL_AVAILABLE = False


def test_rl_service_creation():
    """RLService可以被创建"""
    from services.rl_service import RLService
    svc = RLService()
    assert svc is not None


def test_create_env_raises_without_axon_quant():
    """axon_quant不可用时create_env抛出RuntimeError"""
    import services.rl_service as rl_mod
    from services.rl_service import RLService
    svc = RLService()
    data = pd.DataFrame({"close": [1, 2, 3]})
    # Temporarily patch axon_quant import to simulate missing module
    import axon_quant
    original_rl = getattr(axon_quant, 'rl', None)
    try:
        if hasattr(axon_quant, 'rl'):
            delattr(axon_quant, 'rl')
        with pytest.raises(RuntimeError, match="axon_quant"):
            svc.create_env(data)
    finally:
        if original_rl is not None:
            axon_quant.rl = original_rl


def test_load_data_from_config():
    """_load_data直接返回config.data"""
    from services.rl_service import RLService, RLTrainConfig
    svc = RLService()
    df = pd.DataFrame({"close": [1, 2, 3]})
    config = RLTrainConfig(data=df)
    result = svc._load_data(config)
    assert len(result) == 3


def test_load_data_requires_symbol_or_data():
    """_load_data无data无symbol时抛ValueError"""
    from services.rl_service import RLService, RLTrainConfig
    svc = RLService()
    config = RLTrainConfig()
    with pytest.raises(ValueError, match="需要 config.data 或 config.symbol"):
        svc._load_data(config)


@pytest.mark.skipif(not RL_AVAILABLE, reason="axon_quant.rl not available")
def test_rl_service_creates_environment():
    """RLService能创建训练环境"""
    from services.rl_service import RLService
    svc = RLService()

    data = pd.DataFrame({
        "open": range(100, 200),
        "high": range(105, 205),
        "low": range(95, 195),
        "close": range(101, 201),
        "volume": [1000] * 100,
    })

    env = svc.create_env(data, features=["close"], reward_type="pnl")
    assert env is not None


@pytest.mark.skipif(not RL_AVAILABLE, reason="axon_quant.rl not available")
def test_rl_service_trains_model():
    """RLService能训练模型"""
    from services.rl_service import RLService, RLTrainConfig
    svc = RLService()

    data = pd.DataFrame({
        "open": range(100, 200),
        "high": range(105, 205),
        "low": range(95, 195),
        "close": range(101, 201),
        "volume": [1000] * 100,
    })

    config = RLTrainConfig(
        algorithm="ppo",
        data=data,
        features=["close"],
        reward_type="pnl",
        total_timesteps=100,
    )

    result = svc.train(config)
    assert result.model_id is not None
    assert "steps" in result.metrics


def test_rl_service_walk_forward():
    """RLService能执行Walk-Forward验证"""
    from services.rl_service import RLService
    svc = RLService()

    data = pd.DataFrame({
        "close": range(100, 200),
        "volume": [1000] * 100,
    })

    result = svc.walk_forward_validate(data, n_splits=3, mode="rolling")
    assert "splits" in result
    assert len(result["splits"]) == 3


# =============================================================================
# GymnasiumWrapper observation_space 动态维度推断测试
# =============================================================================


class _FakeEnv:
    """极简假环境 — 用于 GymnasiumWrapper 维度推断测试"""

    def __init__(self, reset_obs, step_result=None):
        self._reset_obs = reset_obs
        self._step_result = step_result or (reset_obs, 0.0, False, False, {})
        self.info = {"symbol": "BTCUSDT"}
        self.reset_count = 0

    def reset(self):
        self.reset_count += 1
        return self._reset_obs

    def step(self, action):
        return self._step_result


def test_gymnasium_wrapper_infer_n_features_dict():
    """dict 形式 obs 走 'features' 键推断维度"""
    from services.rl_service import GymnasiumWrapper

    obs = {"features": [0.0, 0.0, 0.0], "extra": "ignored"}
    assert GymnasiumWrapper._infer_n_features(obs) == 3


def test_gymnasium_wrapper_infer_n_features_dict_empty():
    """dict 但 features 为空时回退 1 维（避免 0 维 Box）"""
    from services.rl_service import GymnasiumWrapper

    assert GymnasiumWrapper._infer_n_features({"features": []}) == 1
    assert GymnasiumWrapper._infer_n_features({"features": None}) == 1


def test_gymnasium_wrapper_infer_n_features_array():
    """array-like 走 len()"""
    import numpy as np
    from services.rl_service import GymnasiumWrapper

    assert GymnasiumWrapper._infer_n_features(np.array([1.0, 2.0, 3.0, 4.0])) == 4
    assert GymnasiumWrapper._infer_n_features([0.0, 0.0]) == 2


def test_gymnasium_wrapper_infer_n_features_fallback():
    """无 __len__ 的标量 → 1"""
    from services.rl_service import GymnasiumWrapper

    assert GymnasiumWrapper._infer_n_features(0.5) == 1


def test_gymnasium_wrapper_observation_space_shape_matches_obs():
    """显式传 n_features 时 observation_space 形状正确"""
    import gymnasium as gym
    from services.rl_service import GymnasiumWrapper

    env = _FakeEnv(reset_obs=[0.0, 0.0, 0.0])
    wrapper = GymnasiumWrapper(env, n_features=3)
    assert isinstance(wrapper.observation_space, gym.spaces.Box)
    assert wrapper.observation_space.shape == (3,)


def test_gymnasium_wrapper_probe_obs_dict_3_features():
    """不传 n_features 时通过探测 reset 推断 3 维（对应 RLBacktestStrategy）"""
    from services.rl_service import GymnasiumWrapper

    env = _FakeEnv(reset_obs={"features": [0.0, 0.0, 0.0]})
    wrapper = GymnasiumWrapper(env)
    assert wrapper.observation_space.shape == (3,)
    # 探测应至少调用 2 次 reset（1 次探测 + 1 次复位）
    assert env.reset_count >= 2


def test_gymnasium_wrapper_probe_obs_array_5_features():
    """探测 array 形式 5 维 obs"""
    from services.rl_service import GymnasiumWrapper

    env = _FakeEnv(reset_obs=[0.1, 0.2, 0.3, 0.4, 0.5])
    wrapper = GymnasiumWrapper(env)
    assert wrapper.observation_space.shape == (5,)


def test_gymnasium_wrapper_probe_failure_fallback_to_1d():
    """探测 reset 抛错时回退到 1 维（不崩溃）"""
    class _BrokenEnv(_FakeEnv):
        def reset(self):
            raise RuntimeError("simulated failure")

    from services.rl_service import GymnasiumWrapper

    wrapper = GymnasiumWrapper(_BrokenEnv(reset_obs=[1, 2, 3]))
    assert wrapper.observation_space.shape == (1,)


def test_gymnasium_wrapper_reset_returns_coerced_obs():
    """reset() 返回 ndarray 且形状匹配 observation_space"""
    from services.rl_service import GymnasiumWrapper

    env = _FakeEnv(reset_obs={"features": [1.0, 2.0, 3.0]})
    wrapper = GymnasiumWrapper(env)
    obs, info = wrapper.reset()
    assert obs.shape == (3,)
    assert obs.dtype.name == "float32"
    assert info == {"symbol": "BTCUSDT"}


def test_gymnasium_wrapper_step_pads_short_obs():
    """step() 收到短 obs 时零填充到正确形状"""
    from services.rl_service import GymnasiumWrapper

    env = _FakeEnv(
        reset_obs={"features": [0.0, 0.0, 0.0]},
        step_result=({"features": [0.5]}, 1.0, False, False, {}),
    )
    wrapper = GymnasiumWrapper(env)
    obs, _, _, _, _ = wrapper.step([0.5])
    assert obs.shape == (3,)
    assert obs[0] == 0.5
    assert obs[1] == 0.0
    assert obs[2] == 0.0


def test_gymnasium_wrapper_step_truncates_long_obs():
    """step() 收到超长 obs 时截断到正确形状"""
    from services.rl_service import GymnasiumWrapper

    env = _FakeEnv(
        reset_obs={"features": [0.0, 0.0, 0.0]},
        step_result=({"features": [1.0, 2.0, 3.0, 4.0, 5.0]}, 1.0, False, False, {}),
    )
    wrapper = GymnasiumWrapper(env)
    obs, _, _, _, _ = wrapper.step([0.5])
    assert obs.shape == (3,)
    assert list(obs) == [1.0, 2.0, 3.0]
