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
