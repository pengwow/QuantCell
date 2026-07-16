# -*- coding: utf-8 -*-
"""RL 服务 — 强化学习训练与推理

核心流程：
1. 获取市场数据 → 转换为 TradingEnv 格式
2. 用 GymnasiumWrapper 包装 TradingEnv（适配 stable-baselines3）
3. 训练模型（PPO/SAC/A2C）
4. 评估 + 保存
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd

from axon_quant import Action
from axon_quant.rl import TradingEnv

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "data" / "rl_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# 动作映射：离散动作 → 交易信号
# 0=hold, 1=buy, 2=sell, 3=close_long, 4=close_short
ACTION_MAP = {0: "hold", 1: "buy", 2: "sell", 3: "close_long", 4: "close_short"}


class TradingEnvWrapper(gym.Env):
    """将 axon_quant TradingEnv 包装为标准 Gymnasium 环境

    支持自定义奖励函数：传入 reward_fn 参数覆盖 TradingEnv 内置奖励
    """

    metadata = {"render_modes": []}

    def __init__(self, trading_env: TradingEnv, reward_fn=None):
        super().__init__()
        self._env = trading_env
        self._reward_fn = reward_fn  # 自定义奖励函数
        self._prev_portfolio = None
        self._step_count = 0
        self._trades = 0

        # 动作空间：离散 5 个动作
        self.action_space = gym.spaces.Discrete(5)

        # 观测空间：用一个 dummy reset 初始化
        dummy_obs, _ = self._raw_obs_to_np(self._env.reset())
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=dummy_obs.shape, dtype=np.float32
        )

    def _raw_obs_to_np(self, raw) -> tuple[np.ndarray, dict]:
        """将 TradingEnv 的原始 obs 转换为 numpy array"""
        if isinstance(raw, dict):
            obs = np.array(raw.get("features", [0.0]), dtype=np.float32)
        elif isinstance(raw, (list, tuple)):
            obs = np.array(raw[0] if len(raw) > 0 else [0.0], dtype=np.float32)
        else:
            obs = np.array(raw, dtype=np.float32)
        return obs, {}

    def reset(self, seed=None, options=None):
        result = self._env.reset()
        obs, info = self._raw_obs_to_np(result)
        self._prev_portfolio = self._env.portfolio_value
        self._step_count = 0
        self._trades = 0
        return obs, info

    def step(self, action):
        result = self._env.step(action)

        # TradingEnv.step() 返回 5 元组
        if len(result) == 5:
            obs_raw, env_reward, terminated, truncated, info = result
        elif len(result) == 3:
            obs_raw, env_reward, info = result
            terminated = info.get("done", False)
            truncated = False
        else:
            raise ValueError(f"Unexpected step result length: {len(result)}")

        obs, _ = self._raw_obs_to_np(obs_raw)

        # 计算自定义奖励
        if self._reward_fn is not None:
            current_portfolio = self._env.portfolio_value
            reward = self._reward_fn(
                prev_portfolio=self._prev_portfolio,
                current_portfolio=current_portfolio,
                action=action,
                step=self._step_count,
                info=info,
            )
            self._prev_portfolio = current_portfolio
        else:
            reward = float(env_reward)

        self._step_count += 1
        if action != 0:  # 非 hold
            self._trades += 1

        return obs, float(reward), bool(terminated), bool(truncated), info

    def render(self):
        pass

    def close(self):
        pass


class RLService:
    """RL 训练与推理服务"""

    def train(self, config: Any, reward_fn=None) -> dict:
        """训练 RL 策略

        Args:
            config: RLTrainConfig (symbol, algorithm, timesteps, etc.)
            reward_fn: 自定义奖励函数，签名 (prev_portfolio, current_portfolio, action, step, info) -> float

        Returns:
            训练结果 dict
        """
        from stable_baselines3 import PPO, SAC, A2C

        logger.info(f"开始训练: {config.symbol} {config.algorithm} {config.timesteps}步")

        # 1. 获取市场数据
        df = self._fetch_market_data(
            config.symbol, config.interval, config.lookback_days
        )

        # 2. 转换为 TradingEnv 格式（list of dicts）
        data_list = self._df_to_env_data(df)

        # 3. 创建并包装环境
        trading_env = TradingEnv(
            config={
                "initial_capital": config.initial_capital,
                "transaction_cost": config.transaction_cost,
                "symbol": config.symbol,
            },
            action_space={"type": "discrete", "n_quantity_bins": 5},
            market_data=data_list,
            reward=config.reward,
        )
        env = TradingEnvWrapper(trading_env, reward_fn=reward_fn)

        # 4. 选择算法
        algo_map = {"ppo": PPO, "sac": SAC, "a2c": A2C}
        algo_cls = algo_map.get(config.algorithm, PPO)

        # 5. 训练
        start_time = time.time()
        model = algo_cls(
            "MlpPolicy",
            env,
            learning_rate=config.learning_rate,
            verbose=1,
            device="auto",
        )
        model.learn(total_timesteps=config.timesteps)
        training_time = time.time() - start_time

        # 6. 保存模型
        output_name = config.output_name or f"{config.symbol}_{config.algorithm}_{int(time.time())}"
        model_path = str(MODELS_DIR / f"{output_name}.zip")
        model.save(model_path)

        # 7. 评估
        metrics = self._evaluate(model, env)

        result = {
            "model_path": model_path,
            "model_name": output_name,
            "total_timesteps": config.timesteps,
            "training_time_secs": round(training_time, 2),
            "algorithm": config.algorithm,
            "symbol": config.symbol,
            **metrics,
        }

        logger.info(f"训练完成: {model_path}, 耗时 {training_time:.1f}s")
        return result

    def predict(self, model_path: str, obs: np.ndarray) -> Action:
        """模型推理

        Args:
            model_path: 模型路径（.zip）
            obs: 观测数据（numpy array）

        Returns:
            Action 对象
        """
        from stable_baselines3 import PPO

        model = PPO.load(model_path)
        action_logits, _ = model.predict(obs.astype(np.float32), deterministic=True)

        action_int = int(action_logits)
        action_type = ACTION_MAP.get(action_int, "hold")

        return Action(
            action_type=action_type,
            confidence=0.8,
            target_position=0.1 if action_type in ("buy", "sell") else 0.0,
            model_id="rl",
            inference_time_us=0,
        )

    def backtest(self, model_path: str, symbol: str, interval: str = "1h",
                 lookback_days: int = 90) -> dict:
        """用训练好的模型回测

        Args:
            model_path: 模型路径
            symbol: 交易对
            interval: K线周期
            lookback_days: 回看天数

        Returns:
            回测结果
        """
        from stable_baselines3 import PPO
        from backtest.backtest_loop import BacktestLoop, RuleStrategy

        # 加载模型
        model = PPO.load(model_path)

        # 获取数据
        df = self._fetch_market_data(symbol, interval, lookback_days)

        # 创建策略包装器
        class RLStrategy(RuleStrategy):
            def __init__(self, model):
                self.model = model
                self._position = 0.0

            def on_bar(self, bar: dict):
                # 构建观测（简化：只用 close 和 volume）
                obs = np.array([bar["close"], bar["volume"]], dtype=np.float32)
                action_logits, _ = self.model.predict(obs, deterministic=True)
                action_int = int(action_logits)
                action_type = ACTION_MAP.get(action_int, "hold")

                if action_type == "buy" and self._position <= 0:
                    self._position = 0.1
                    return Action("buy", 0.8, 0.1, "rl_model", 0)
                elif action_type == "sell" and self._position >= 0:
                    self._position = -0.1
                    return Action("sell", 0.8, 0.1, "rl_model", 0)
                elif action_type == "close_long" and self._position > 0:
                    self._position = 0.0
                    return Action("sell", 0.9, 0.1, "rl_model", 0)
                elif action_type == "close_short" and self._position < 0:
                    self._position = 0.0
                    return Action("buy", 0.9, 0.1, "rl_model", 0)

                return Action("hold", 0.0, 0.0, "rl_model", 0)

        strategy = RLStrategy(model)
        loop = BacktestLoop(initial_cash=100_000)
        result = loop.run(strategy, df, symbol)

        return {
            "total_pnl": result.total_pnl,
            "final_nav": result.final_nav,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "fills": result.fills,
            "total_fees": result.total_fees,
            "bar_count": result.bar_count,
        }

    def list_models(self) -> list[dict]:
        """列出已训练模型"""
        models = []
        for f in MODELS_DIR.glob("*.zip"):
            models.append({
                "name": f.stem,
                "path": str(f),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        return sorted(models, key=lambda x: x["name"])

    def _fetch_market_data(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        """获取市场数据（优先本地 parquet，fallback 到 Binance API）"""
        # 1. 尝试本地 parquet
        local_path = Path(__file__).parent.parent / "data" / "source" / "crypto" / "spot" / "klines" / interval / f"{symbol}.parquet"
        if local_path.exists():
            df = pd.read_parquet(local_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="us")
            df.set_index("timestamp", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = df[col].astype(float)
            # 标准化列名为大写
            col_map = {c: c.capitalize() for c in ["open", "high", "low", "close", "volume"] if c in df.columns}
            df = df.rename(columns=col_map)
            logger.info(f"从本地加载 {len(df)} 根K线: {local_path}")
            return df[["Open", "High", "Low", "Close", "Volume"]]

        # 2. Fallback 到 Binance API
        limit = min(lookback_days * 96, 1000)  # 15min = 96根/天
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QuantCell/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            df = pd.DataFrame(data, columns=[
                "timestamp", "Open", "High", "Low", "Close", "Volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore",
            ])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = df[col].astype(float)
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            raise

    def _df_to_env_data(self, df: pd.DataFrame) -> list[dict]:
        """将 DataFrame 转换为 TradingEnv 需要的 list[dict] 格式"""
        data = []
        for idx, row in df.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1e9) if not isinstance(idx, (int, float)) else int(idx)
            data.append({
                "timestamp": ts,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        return data

    def _evaluate(self, model, env, n_episodes: int = 3) -> dict:
        """评估模型"""
        rewards = []
        for _ in range(n_episodes):
            obs, _ = env.reset()
            total_reward = 0
            done = False
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                total_reward += reward
                done = terminated or truncated
            rewards.append(total_reward)

        return {
            "eval_reward_mean": float(np.mean(rewards)),
            "eval_reward_std": float(np.std(rewards)),
        }
