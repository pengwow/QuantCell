"""RL Training Pipeline Service.

Unified entry point for RL training, HPO, Walk-Forward, and model registry.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.hpo_runner import HPORunner
from backtest.walk_forward import WalkForwardService

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "data" / "models"


@dataclass
class RLTrainConfig:
    """RL training configuration."""
    algorithm: str = "ppo"
    data: pd.DataFrame | None = None
    symbol: str = ""
    interval: str = "1h"
    candle_type: str = "spot"
    start: str | None = None
    end: str | None = None
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
    model_path: str | None = None
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
        "transaction_cost": 0.0001,
        "slippage": 0.00001,
        "max_steps": max_steps,
        "seed": seed,
        "symbol": symbol,
        "return_window": 50,
    }


try:
    import gymnasium as gym

    class GymnasiumWrapper(gym.Env):
        """Wrap axon_quant TradingEnv to be Gymnasium-compatible for SB3."""

        def __init__(self, env, max_steps: int = 0):
            super().__init__()
            self._env = env
            self._done = False
            self._current_step = 0
            if max_steps > 0:
                self._max_steps = max_steps
            elif hasattr(env, 'info') and isinstance(env.info, dict):
                self._max_steps = 999_999_999
            else:
                self._max_steps = 50000

            self.observation_space = gym.spaces.Box(
                low=-np.inf, high=np.inf, shape=(2,), dtype=np.float32
            )
            self.action_space = gym.spaces.Box(
                low=0.0, high=1.0, shape=(1,), dtype=np.float32
            )

        def reset(self, seed=None, options=None):
            """Reset environment."""
            obs = self._env.reset()
            self._done = False
            self._current_step = 0
            info = self._env.info if hasattr(self._env, 'info') and isinstance(self._env.info, dict) else {}
            if isinstance(obs, dict):
                features = obs.get('features', [0.0, 0.0])
                return np.array(features, dtype=np.float32), info
            return np.array(obs, dtype=np.float32), info

        def step(self, action):
            """Take a step in the environment."""
            if isinstance(action, np.ndarray):
                action = action.tolist()
            # axon_quant TradingEnv only accepts positive actions (buy quantity)
            action = [max(0.0, min(1.0, a)) for a in action]

            result = self._env.step(action)
            self._current_step += 1

            if isinstance(result, tuple) and len(result) >= 4:
                obs = result[0]
                reward = result[1]
                done = result[2]
                if len(result) >= 5:
                    info = result[4] if isinstance(result[4], dict) else {}
                else:
                    info = result[3] if isinstance(result[3], dict) else {}
            else:
                obs = result
                reward = 0.0
                done = False
                info = {}

            if isinstance(obs, dict):
                features = obs.get('features', [0.0, 0.0])
                obs = np.array(features, dtype=np.float32)
            else:
                obs = np.array(obs, dtype=np.float32)

            truncated = self._current_step >= self._max_steps
            self._done = done or truncated

            return obs, float(reward), done, truncated, info or {}

        def close(self):
            """Close environment."""
            pass

except ImportError:
    GymnasiumWrapper = None


class RLService:
    """RL training pipeline service."""

    def __init__(self):
        self._hpo = HPORunner()
        self._wf = WalkForwardService()
        self._models_dir = MODELS_DIR
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_data(self, config: RLTrainConfig) -> pd.DataFrame:
        """Load data from config.data or BacktestDataProvider."""
        if config.data is not None:
            return config.data
        if config.symbol:
            from backtest.data_provider import BacktestDataProvider
            provider = BacktestDataProvider()
            return provider.load_klines(
                config.symbol, config.interval, config.candle_type,
                config.start, config.end,
            )
        raise ValueError("需要 config.data 或 config.symbol")

    def create_env(
        self,
        data: pd.DataFrame,
        features: list[str] | None = None,
        reward_type: str = "pnl",
    ) -> Any:
        """Create an RL training environment.

        Requires axon_quant. Raises RuntimeError if not available.
        """
        import axon_quant
        if not hasattr(axon_quant, 'rl') or not hasattr(axon_quant.rl, 'TradingEnv'):
            raise RuntimeError(
                "axon_quant.rl.TradingEnv 不可用，请安装 axon_quant: pip install axon_quant"
            )

        df = data.copy()
        df.columns = [c.lower() for c in df.columns]
        if 'timestamp' not in df.columns:
            df['timestamp'] = range(len(df))

        market_data = df.to_dict("records")
        config = _make_env_config(max_steps=len(df))
        return axon_quant.rl.TradingEnv(config=config, market_data=market_data, reward=reward_type)

    def train(self, config: RLTrainConfig) -> RLTrainResult:
        """Execute RL training with stable-baselines3 and save model.

        When config.walk_forward=True, runs Walk-Forward validation first,
        then trains final model on full data with OOS evaluation.
        """
        data = self._load_data(config)

        logger.info(f"[RLService] 开始训练: algorithm={config.algorithm}, timesteps={config.total_timesteps}, reward={config.reward_type}")
        start_time = time.time()

        wf_result = None
        if config.walk_forward:
            from rl.walk_forward_rl import RLWalkForwardService
            wf_svc = RLWalkForwardService()

            def env_factory(d: pd.DataFrame):
                env = self.create_env(d, config.features, config.reward_type)
                return GymnasiumWrapper(env)

            try:
                from stable_baselines3 import PPO, SAC, DQN
            except ImportError:
                raise RuntimeError(
                    "缺少RL训练依赖，请安装: pip install stable-baselines3 gymnasium torch"
                )

            algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
            algo_cls = algo_map.get(config.algorithm)
            if algo_cls is None:
                raise ValueError(f"Unknown algorithm: {config.algorithm}")

            wf_result = wf_svc.validate(
                data=data,
                env_factory=env_factory,
                algo_cls=algo_cls,
                n_splits=config.wf_splits,
                total_timesteps=config.total_timesteps,
            )

        env = self.create_env(data, config.features, config.reward_type)

        try:
            from stable_baselines3 import PPO, SAC, DQN
        except ImportError:
            raise RuntimeError(
                "缺少RL训练依赖，请安装: pip install stable-baselines3 gymnasium torch"
            )

        algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
        algo_cls = algo_map.get(config.algorithm)
        if algo_cls is None:
            raise ValueError(f"Unknown algorithm: {config.algorithm}")

        logger.info(f"[RLService] 使用 {algo_cls.__name__} 训练...")

        wrapped_env = GymnasiumWrapper(env)
        model = algo_cls("MlpPolicy", wrapped_env, verbose=0)
        model.learn(total_timesteps=config.total_timesteps)

        model_id = f"{config.model_name}_{config.algorithm}_{int(time.time())}"
        model_path = str(MODELS_DIR / f"{model_id}.zip")
        model.save(model_path)
        logger.info(f"[RLService] 模型已保存: {model_path}")

        wrapped_env.close()

        elapsed = time.time() - start_time
        logger.info(f"[RLService] 训练完成: elapsed={elapsed:.1f}s")

        return RLTrainResult(
            model_id=model_id,
            model_path=model_path,
            metrics={
                "steps": config.total_timesteps,
                "algorithm": config.algorithm,
                "elapsed_seconds": round(elapsed, 2),
                "model_path": model_path,
            },
            walk_forward=wf_result,
        )

    def load_model(self, model_path: str) -> Any:
        """Load a trained model from path."""
        try:
            from stable_baselines3 import PPO, SAC, DQN
            if "ppo" in model_path.lower():
                return PPO.load(model_path)
            elif "sac" in model_path.lower():
                return SAC.load(model_path)
            elif "dqn" in model_path.lower():
                return DQN.load(model_path)
            else:
                return PPO.load(model_path)
        except Exception as e:
            logger.error(f"[RLService] 加载模型失败: {e}")
            return None

    def list_saved_models(self) -> list[dict[str, Any]]:
        """List all saved models in the models directory."""
        models = []
        if MODELS_DIR.exists():
            for f in MODELS_DIR.glob("*.zip"):
                models.append({
                    "name": f.stem,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "created": f.stat().st_ctime,
                })
        return models

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

    def run_backtest(
        self,
        model_path: str,
        symbol: str,
        interval: str = "1h",
        candle_type: str = "spot",
        initial_capital: float = 100_000.0,
        reward_type: str = "pnl",
    ) -> dict[str, Any]:
        """Run a trained RL model through axon_quant TradingEnv for backtesting.

        Uses TradingEnv as the simulation engine and the SB3 model for inference.
        Returns evaluation metrics (PnL, Sharpe, drawdown, etc.).
        """
        from backtest.data_provider import BacktestDataProvider
        from rl.evaluation import evaluate_model

        provider = BacktestDataProvider()
        data = provider.load_klines(symbol, interval, candle_type)
        if data.empty:
            raise ValueError(f"无法加载 {symbol} {interval} 数据")

        env = self.create_env(data, reward_type=reward_type)
        wrapped_env = GymnasiumWrapper(env)

        model = self.load_model(model_path)
        if model is None:
            raise RuntimeError(f"无法加载模型: {model_path}")

        metrics = evaluate_model(model, wrapped_env)
        wrapped_env.close()

        return {
            "symbol": symbol,
            "interval": interval,
            "data_bars": len(data),
            "initial_capital": initial_capital,
            "total_pnl": metrics.total_pnl,
            "total_return_pct": metrics.total_return_pct,
            "sharpe_ratio": metrics.sharpe_ratio,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "win_rate": metrics.win_rate,
            "num_trades": metrics.num_trades,
            "profit_factor": metrics.profit_factor,
        }
