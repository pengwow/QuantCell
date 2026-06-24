"""RL Training Pipeline Service.

Unified entry point for RL training, HPO, Walk-Forward, and model registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backtest.hpo_runner import HPORunner
from backtest.walk_forward import WalkForwardService


@dataclass
class RLTrainConfig:
    """RL training configuration."""
    algorithm: str = "ppo"
    data: pd.DataFrame | None = None
    features: list[str] = field(default_factory=lambda: ["close"])
    reward_type: str = "pnl"
    total_timesteps: int = 10_000
    model_name: str = "rl_model"
    walk_forward: bool = False
    wf_splits: int = 5


@dataclass
class RLTrainResult:
    """RL training result."""
    model_id: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    walk_forward: dict[str, Any] | None = None


def _make_env_config(
    initial_capital: float = 100_000.0,
    max_steps: int = 500,
    seed: int = 42,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    """Create default environment config."""
    return {
        "initial_capital": initial_capital,
        "transaction_cost": 0.001,
        "slippage": 0.0001,
        "max_steps": max_steps,
        "seed": seed,
        "symbol": symbol,
        "return_window": 50,
    }


class RLService:
    """RL training pipeline service."""

    def __init__(self):
        self._hpo = HPORunner()
        self._wf = WalkForwardService()

    def create_env(
        self,
        data: pd.DataFrame,
        features: list[str] | None = None,
        reward_type: str = "pnl",
    ) -> Any:
        """Create an RL training environment."""
        from axon_quant.rl import TradingEnv
        market_data = data.to_dict("records")
        config = _make_env_config()
        return TradingEnv(config=config, market_data=market_data, reward=reward_type)

    def train(self, config: RLTrainConfig) -> RLTrainResult:
        """Execute RL training."""
        if config.data is None:
            raise ValueError("config.data is required")

        env = self.create_env(config.data, config.features, config.reward_type)
        obs, info = env.reset()
        total_reward = 0.0
        steps = 0

        for _ in range(min(config.total_timesteps, 1000)):
            action = env.action_space.sample()
            obs, reward, done, truncated, info = env.step(action)
            total_reward += reward
            steps += 1
            if done or truncated:
                obs, info = env.reset()

        return RLTrainResult(
            model_id=f"mock_{config.model_name}",
            metrics={"total_reward": total_reward, "steps": steps, "algorithm": config.algorithm},
        )

    def optimize_hyperparameters(
        self, objective_fn: Any, param_space: dict[str, Any], n_trials: int = 10,
    ) -> dict[str, Any]:
        """Execute hyperparameter optimization."""
        return self._hpo.optimize(objective_fn, param_space, n_trials)

    def walk_forward_validate(
        self, data: pd.DataFrame, n_splits: int = 5, mode: str = "rolling",
    ) -> dict[str, Any]:
        """Execute Walk-Forward validation."""
        return self._wf.validate(strategy_fn=None, data=data, n_splits=n_splits, mode=mode)
