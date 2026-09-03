"""RL Training Pipeline Service.

Unified entry point for RL training, HPO, Walk-Forward, and model registry.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from backtest.hpo_runner import HPORunner
from backtest.walk_forward import WalkForwardService
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    import pandas as pd

logger = get_logger(__name__, LogType.APPLICATION)

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

        def __init__(self, env, max_steps: int = 0, n_features: int | None = None):
            super().__init__()
            self._env = env
            self._done = False
            self._current_step = 0
            if max_steps > 0:
                self._max_steps = max_steps
            elif hasattr(env, "info") and isinstance(env.info, dict):
                self._max_steps = 999_999_999
            else:
                self._max_steps = 50000

            # 动态确定 observation_space 维度：
            # 1) 调用方显式指定 → 直接采用
            # 2) 否则探测一次 env.reset() 拿到首帧 obs 推断维度
            if n_features is not None and n_features > 0:
                inferred = n_features
            else:
                probe_obs = self._probe_obs(env)
                inferred = self._infer_n_features(probe_obs)
            self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(inferred,), dtype=np.float32)
            self.action_space = gym.spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        @staticmethod
        def _probe_obs(env):
            """探测性地调用一次 env.reset() 推断 obs 维度，复位后再 reset 一次保证初始状态干净。"""
            try:
                probe = env.reset()
            except Exception:
                # 探测失败时用占位单维 obs，避免构造阶段崩溃
                return np.zeros(1, dtype=np.float32)
            # 复位 env 到探测前的状态
            with contextlib.suppress(Exception):
                env.reset()
            return probe

        @staticmethod
        def _infer_n_features(obs) -> int:
            """从 obs 推断特征维度：dict 走 'features' 键，其他走 len()。"""
            if isinstance(obs, dict) and "features" in obs:
                features = obs["features"]
                return len(features) if features is not None and len(features) > 0 else 1
            if hasattr(obs, "__len__"):
                length = len(obs)
                return length if length > 0 else 1
            return 1

        @staticmethod
        def _coerce_obs(obs, observation_space) -> np.ndarray:
            """统一 obs 转换：dict 取 'features'，array-like 直接转 ndarray，并按 space 形状校验。"""
            if isinstance(obs, dict) and "features" in obs:
                arr = np.asarray(obs["features"], dtype=np.float32)
            else:
                arr = np.asarray(obs, dtype=np.float32)
            expected = observation_space.shape[0]
            if arr.shape[0] != expected:
                # 维度不匹配时截断或零填充到正确形状，避免 SB3 训练时抛 shape 错误
                flat = arr.flatten()
                if flat.size >= expected:
                    arr = flat[:expected]
                else:
                    padded = np.zeros(expected, dtype=np.float32)
                    padded[: flat.size] = flat
                    arr = padded
            return arr

        def reset(self, seed=None, options=None):
            """Reset environment."""
            obs = self._env.reset()
            self._done = False
            self._current_step = 0
            info = self._env.info if hasattr(self._env, "info") and isinstance(self._env.info, dict) else {}
            obs_arr = self._coerce_obs(obs, self.observation_space)
            return obs_arr, info

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

            obs = self._coerce_obs(obs, self.observation_space)
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
                config.symbol,
                config.interval,
                config.candle_type,
                config.start,
                config.end,
            )
        msg = "需要 config.data 或 config.symbol"
        raise ValueError(msg)

    def create_env(
        self,
        data: pd.DataFrame,
        features: list[str] | None = None,
        reward_type: str = "pnl",
    ) -> Any:
        """Create an RL training environment.

        Requires axon_quant. Raises RuntimeError if not available.
        """
        # 走适配层检查可用性,避免业务代码直连 axon_quant
        from axon_bridge import rl as _rl_bridge

        if not hasattr(_rl_bridge, "TradingEnv"):
            msg = "axon_quant.rl.TradingEnv 不可用，请安装 axon_quant: pip install axon_quant"
            raise RuntimeError(msg)

        df = data.copy()
        df.columns = [c.lower() for c in df.columns]
        if "timestamp" not in df.columns:
            df["timestamp"] = range(len(df))

        market_data = df.to_dict("records")
        config = _make_env_config(max_steps=len(df))
        return _rl_bridge.TradingEnv(config=config, market_data=market_data, reward=reward_type)

    def train(self, config: RLTrainConfig) -> RLTrainResult:
        """Execute RL training with stable-baselines3 and save model.

        When config.walk_forward=True, runs Walk-Forward validation first,
        then trains final model on full data with OOS evaluation.
        """
        data = self._load_data(config)

        logger.info(
            f"[RLService] 开始训练: algorithm={config.algorithm}, timesteps={config.total_timesteps}, reward={config.reward_type}"
        )
        start_time = time.time()

        wf_result = None
        if config.walk_forward:
            from rl.walk_forward_rl import RLWalkForwardService

            wf_svc = RLWalkForwardService()

            def env_factory(d: pd.DataFrame):
                env = self.create_env(d, config.features, config.reward_type)
                return GymnasiumWrapper(env)

            try:
                from stable_baselines3 import DQN, PPO, SAC
            except ImportError:
                msg = "缺少RL训练依赖，请安装: pip install stable-baselines3 gymnasium torch"
                raise RuntimeError(msg)

            algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
            algo_cls = algo_map.get(config.algorithm)
            if algo_cls is None:
                msg = f"Unknown algorithm: {config.algorithm}"
                raise ValueError(msg)

            wf_result = wf_svc.validate(
                data=data,
                env_factory=env_factory,
                algo_cls=algo_cls,
                n_splits=config.wf_splits,
                total_timesteps=config.total_timesteps,
            )

        env = self.create_env(data, config.features, config.reward_type)

        try:
            from stable_baselines3 import DQN, PPO, SAC
        except ImportError:
            msg = "缺少RL训练依赖，请安装: pip install stable-baselines3 gymnasium torch"
            raise RuntimeError(msg)

        algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
        algo_cls = algo_map.get(config.algorithm)
        if algo_cls is None:
            msg = f"Unknown algorithm: {config.algorithm}"
            raise ValueError(msg)

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
            from stable_baselines3 import DQN, PPO, SAC

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
                models.append(
                    {
                        "name": f.stem,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                        "created": f.stat().st_ctime,
                    }
                )
        return models

    def optimize_hyperparameters(
        self,
        objective_fn: Any,
        param_space: dict[str, Any],
        n_trials: int = 10,
    ) -> dict[str, Any]:
        """Execute hyperparameter optimization."""
        return self._hpo.optimize(objective_fn, param_space, n_trials)

    def walk_forward_validate(
        self,
        data: pd.DataFrame,
        n_splits: int = 5,
        mode: str = "rolling",
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
            msg = f"无法加载 {symbol} {interval} 数据"
            raise ValueError(msg)

        env = self.create_env(data, reward_type=reward_type)
        wrapped_env = GymnasiumWrapper(env)

        model = self.load_model(model_path)
        if model is None:
            msg = f"无法加载模型: {model_path}"
            raise RuntimeError(msg)

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
