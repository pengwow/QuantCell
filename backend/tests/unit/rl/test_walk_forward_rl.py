"""Tests for rl/walk_forward_rl.py — RLWalkForwardService."""

import pandas as pd
import pytest

from rl.evaluation import EvaluationMetrics
from rl.walk_forward_rl import RLWalkForwardService, _aggregate_folds, _metrics_to_dict


def _make_data(n: int = 200) -> pd.DataFrame:
    """Create synthetic OHLCV data for testing."""
    import random

    rng = random.Random(42)
    data = []
    price = 100.0
    for _i in range(n):
        ret = 0.0002 + 0.02 * rng.gauss(0, 1)
        close_p = price * (1 + ret)
        data.append(
            {
                "open": price,
                "high": max(price, close_p) * 1.01,
                "low": min(price, close_p) * 0.99,
                "close": close_p,
                "volume": rng.uniform(500_000, 2_000_000),
            }
        )
        price = close_p
    return pd.DataFrame(data)


def test_metrics_to_dict():
    """_metrics_to_dict converts EvaluationMetrics to dict."""
    m = EvaluationMetrics(total_pnl=100.0, sharpe_ratio=1.5, win_rate=0.6)
    d = _metrics_to_dict(m)
    assert d["total_pnl"] == 100.0
    assert d["sharpe_ratio"] == 1.5
    assert d["win_rate"] == 0.6
    assert "max_drawdown_pct" in d


def test_aggregate_folds_empty():
    """No valid folds → n_valid_folds=0."""
    result = _aggregate_folds([{"fold": 0, "error": "fail"}])
    assert result["n_valid_folds"] == 0
    assert result["mean"] == {}


def test_aggregate_folds_with_data():
    """Aggregate two valid folds → mean and std computed."""
    folds = [
        {
            "fold": 0,
            "oos_metrics": {
                "total_pnl": 100,
                "sharpe_ratio": 1.0,
                "total_return_pct": 1.0,
                "max_drawdown_pct": -5.0,
                "win_rate": 0.6,
                "num_trades": 10,
                "profit_factor": 1.5,
            },
        },
        {
            "fold": 1,
            "oos_metrics": {
                "total_pnl": 200,
                "sharpe_ratio": 2.0,
                "total_return_pct": 2.0,
                "max_drawdown_pct": -3.0,
                "win_rate": 0.7,
                "num_trades": 20,
                "profit_factor": 2.5,
            },
        },
    ]
    result = _aggregate_folds(folds)
    assert result["n_valid_folds"] == 2
    assert result["mean"]["total_pnl"] == 150.0
    assert result["mean"]["sharpe_ratio"] == 1.5
    assert result["std"]["total_pnl"] == 50.0


def _mock_env_factory(data: pd.DataFrame):
    """Create a mock Gymnasium env that returns deterministic rewards."""
    import gymnasium as gym
    import numpy as np

    class MockTradingEnv(gym.Env):
        def __init__(self, data):
            super().__init__()
            self._data = data
            self._step = 0
            self._nav = 100_000.0
            self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(5,), dtype=np.float32)
            self.action_space = gym.spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)

        def reset(self, seed=None, options=None):
            self._step = 0
            self._nav = 100_000.0
            return np.zeros(5, dtype=np.float32), {}

        def step(self, action):
            self._step += 1
            row = self._data.iloc[self._step - 1]
            ret = (row["close"] - row["open"]) / row["open"]
            position = float(action[0])
            self._nav *= 1 + position * ret * 0.01
            done = self._step >= len(self._data)
            return (
                np.zeros(5, dtype=np.float32),
                position * ret,
                done,
                False,
                {"nav": self._nav},
            )

    return MockTradingEnv(data)


class MockAlgo:
    """Mock SB3 algorithm for testing without real SB3."""

    def __init__(self, policy, env, verbose=0, **kwargs):
        self._env = env

    def learn(self, total_timesteps=1000):
        pass

    def predict(self, obs, deterministic=True):
        import numpy as np

        return np.array([0.1], dtype=np.float32), None


@pytest.mark.skipif(
    not hasattr(RLWalkForwardService, "__init__"),
    reason="WalkForwardService not available",
)
def test_wf_service_basic():
    """RLWalkForwardService runs a basic WF validation."""
    svc = RLWalkForwardService()
    data = _make_data(200)

    result = svc.validate(
        data=data,
        env_factory=_mock_env_factory,
        algo_cls=MockAlgo,
        n_splits=3,
        train_ratio=0.7,
        mode="rolling",
        total_timesteps=100,
    )

    assert result["n_splits"] == 3
    assert result["mode"] == "rolling"
    assert len(result["folds"]) > 0

    # Each fold should have oos_metrics or error
    for fold in result["folds"]:
        assert "fold" in fold
        assert "train_size" in fold
        assert "test_size" in fold
        assert "oos_metrics" in fold or "error" in fold

    # Aggregate should exist
    assert "aggregate" in result
    assert "mean" in result["aggregate"]
    assert "std" in result["aggregate"]


def test_wf_service_expanding_mode():
    """RLWalkForwardService works in expanding mode."""
    svc = RLWalkForwardService()
    data = _make_data(200)

    result = svc.validate(
        data=data,
        env_factory=_mock_env_factory,
        algo_cls=MockAlgo,
        n_splits=3,
        train_ratio=0.7,
        mode="expanding",
        total_timesteps=50,
    )

    assert result["mode"] == "expanding"
    assert len(result["folds"]) > 0
