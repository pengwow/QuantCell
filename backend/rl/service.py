"""RL 服务 — 强化学习训练与推理

核心流程：
1. 获取市场数据 → 转换为 TradingEnv 格式
2. 用 GymnasiumWrapper 包装 TradingEnv（适配 stable-baselines3）
3. 训练模型（PPO/SAC/A2C）
4. 评估 + 保存
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gymnasium as gym
import numpy as np
import pandas as pd

from axon_bridge import Action
from axon_bridge.rl import TradingEnv

if TYPE_CHECKING:
    from collections.abc import Callable
    from queue import Queue

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "data" / "rl_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# 动作映射：离散动作 → 交易信号
# 0=hold, 1=buy, 2=sell, 3=close_long, 4=close_short
ACTION_MAP = {0: "hold", 1: "buy", 2: "sell", 3: "close_long", 4: "close_short"}


class TrainingProgressCallback:
    """SB3 训练回调类 — 捕获训练进度并推送

    使用方式：
        callback = TrainingProgressCallback(on_progress=on_progress_fn)
        model.learn(total_timesteps=N, callback=callback)

    或使用队列模式：
        queue = Queue()
        callback = TrainingProgressCallback(queue=queue)
        model.learn(total_timesteps=N, callback=callback)
        # 从队列读取进度
        while True:
            progress = queue.get()
            if progress["type"] == "complete":
                break
            print(progress)
    """

    def __init__(
        self,
        queue: Queue | None = None,
        on_progress: Callable[[dict], None] | None = None,
        log_interval: int = 1000,
    ):
        self.queue = queue
        self.on_progress = on_progress
        self.log_interval = log_interval
        self.start_time = time.time()
        self.episode_rewards = []
        self.total_timesteps_done = 0
        self.num_episodes = 0

    def _send_progress(self, data: dict):
        """发送进度数据"""
        if self.queue:
            self.queue.put(data)
        if self.on_progress:
            self.on_progress(data)

    def on_step(self, locals_dict: dict, globals_dict: dict) -> bool:
        """每步回调（不常用）"""
        return True

    def on_rollout_start(self) -> None:
        """每次 rollout 开始"""
        pass

    def on_rollout_end(self) -> None:
        """每次 rollout 结束（常用于记录指标）"""
        pass

    def on_training_start(self) -> None:
        """训练开始"""
        self.start_time = time.time()
        self.episode_rewards = []
        self.total_timesteps_done = 0
        self.num_episodes = 0
        self._send_progress(
            {
                "type": "start",
                "timestamp": time.time(),
                "message": "训练开始",
            }
        )

    def on_training_end(self) -> None:
        """训练结束"""
        elapsed_time = time.time() - self.start_time
        self._send_progress(
            {
                "type": "complete",
                "timestamp": time.time(),
                "elapsed_time": round(elapsed_time, 2),
                "total_timesteps": self.total_timesteps_done,
                "num_episodes": self.num_episodes,
                "mean_reward": float(np.mean(self.episode_rewards)) if self.episode_rewards else 0.0,
                "max_reward": float(np.max(self.episode_rewards)) if self.episode_rewards else 0.0,
                "min_reward": float(np.min(self.episode_rewards)) if self.episode_rewards else 0.0,
            }
        )

    def on_policy_update(self) -> None:
        """策略更新时（每 update_freq 步）"""
        pass

    def on_step_end(self, step, done, info) -> None:
        """每步结束（自定义方法，需手动调用）"""
        self.total_timesteps_done = step + 1

        if done:
            self.num_episodes += 1
            if "episode" in info:
                episode_reward = info["episode"]["r"]
                self.episode_rewards.append(float(episode_reward))

                # 每 log_interval 步或每 episode 发送进度
                if self.total_timesteps_done % self.log_interval == 0:
                    elapsed_time = time.time() - self.start_time
                    mean_reward = (
                        float(np.mean(self.episode_rewards[-10:]))
                        if len(self.episode_rewards) >= 10
                        else float(np.mean(self.episode_rewards))
                    )

                    self._send_progress(
                        {
                            "type": "progress",
                            "timestamp": time.time(),
                            "timestep": self.total_timesteps_done,
                            "episode": self.num_episodes,
                            "episode_reward": float(episode_reward),
                            "mean_reward": mean_reward,
                            "elapsed_time": round(elapsed_time, 2),
                        }
                    )


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
        self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=dummy_obs.shape, dtype=np.float32)

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
            msg = f"Unexpected step result length: {len(result)}"
            raise ValueError(msg)

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

    def _train_internal(
        self,
        config: Any,
        reward_fn=None,
        verbose: int = 1,
        callback=None,
        progress_callback=None,
    ) -> dict:
        """内部训练方法（被 train 和 train_stream 调用）

        Args:
            config: RLTrainConfig (symbol, algorithm, timesteps, etc.)
            reward_fn: 自定义奖励函数
            verbose: SB3 日志级别
            callback: SB3 回调对象
            progress_callback: 进度回调函数 (dict) -> None

        Returns:
            训练结果 dict
        """
        from stable_baselines3 import A2C, PPO, SAC

        logger.info(f"开始训练: {config.symbol} {config.algorithm} {config.timesteps}步")

        # 1. 获取市场数据
        df = self._fetch_market_data(config.symbol, config.interval, config.lookback_days)
        if progress_callback:
            progress_callback(
                {
                    "type": "info",
                    "message": f"加载数据完成: {len(df)} 条",
                    "timestamp": time.time(),
                }
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

        # 5. 创建模型并训练
        start_time = time.time()
        model = algo_cls(
            "MlpPolicy",
            env,
            learning_rate=config.learning_rate,
            verbose=verbose,
            device="auto",
        )
        model.learn(
            total_timesteps=config.timesteps,
            callback=callback,
            progress_bar=False,
        )
        training_time = time.time() - start_time

        # 6. 保存模型和元数据
        output_name = config.output_name or f"{config.symbol}_{config.algorithm}_{int(time.time())}"
        model_path = str(MODELS_DIR / f"{output_name}.zip")
        model.save(model_path)

        # 保存模型元数据（用于 predict 时确定算法类型）
        self._save_model_metadata(output_name, config.algorithm)

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

    def train(self, config: Any, reward_fn=None) -> dict:
        """训练 RL 策略

        Args:
            config: RLTrainConfig (symbol, algorithm, timesteps, etc.)
            reward_fn: 自定义奖励函数，签名 (prev_portfolio, current_portfolio, action, step, info) -> float

        Returns:
            训练结果 dict
        """
        return self._train_internal(config, reward_fn=reward_fn, verbose=1)

    def train_stream(self, config: Any, progress_queue: Queue, reward_fn=None) -> dict:
        """流式训练 RL 策略（通过队列推送进度）

        Args:
            config: RLTrainConfig (symbol, algorithm, timesteps, etc.)
            progress_queue: 进度队列，用于推送训练进度
            reward_fn: 自定义奖励函数

        Returns:
            训练结果 dict
        """
        logger.info(f"开始流式训练: {config.symbol} {config.algorithm} {config.timesteps}步")

        # 创建回调并开始训练
        callback = TrainingProgressCallback(queue=progress_queue)

        def progress_callback(data: dict):
            progress_queue.put(data)

        return self._train_internal(
            config,
            reward_fn=reward_fn,
            verbose=0,
            callback=callback,
            progress_callback=progress_callback,
        )

    def _save_model_metadata(self, model_name: str, algorithm: str) -> None:
        """保存模型元数据（原子写入，防止并发竞争条件）"""
        metadata_path = MODELS_DIR / f"{model_name}_metadata.json"
        metadata = {
            "algorithm": algorithm,
            "created_at": time.time(),
            "model_name": model_name,
        }

        # 原子写入：先写临时文件，再重命名（POSIX 保证原子性）
        fd, tmp_path = tempfile.mkstemp(dir=str(MODELS_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(metadata, f)
            os.replace(tmp_path, str(metadata_path))
        except Exception:
            # 清理临时文件
            if os.path.exists(tmp_path):
                with contextlib.suppress(Exception):
                    os.unlink(tmp_path)
            raise

    def _load_model_metadata(self, model_name: str) -> dict | None:
        """加载模型元数据"""
        metadata_path = MODELS_DIR / f"{model_name}_metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                return json.load(f)
        return None

    def predict(self, model_path: str, obs: np.ndarray) -> Action:
        """模型推理（支持多种算法）

        Args:
            model_path: 模型路径（.zip）
            obs: 观测数据（numpy array）

        Returns:
            Action 对象

        Raises:
            ValueError: 如果无法确定算法类型且没有元数据文件
        """
        from stable_baselines3 import A2C, PPO, SAC

        # 从模型路径提取模型名称，查找元数据
        model_name = Path(model_path).stem
        metadata = self._load_model_metadata(model_name)

        # 根据元数据或路径推断算法类型
        algo_map = {"ppo": PPO, "sac": SAC, "a2c": A2C}
        algorithm = None

        # 优先使用元数据
        if metadata and metadata.get("algorithm") in algo_map:
            algorithm = metadata["algorithm"]
        else:
            # 从模型名称推断（格式：symbol_algorithm_timestamp 或 symbol_algorithm）
            # 从末尾开始查找，因为交易对可能包含下划线（如 BTC_USDT）
            parts = model_name.split("_")
            # 检查倒数几个部分
            for i in range(min(3, len(parts)), 0, -1):
                candidate = parts[-i].lower()
                if candidate in algo_map:
                    algorithm = candidate
                    break

        # 如果仍无法确定，抛出明确错误
        if algorithm is None:
            msg = (
                f"无法确定模型 '{model_name}' 的算法类型。"
                f"请确保存在元数据文件 '{model_name}_metadata.json'，"
                f"或模型名称包含算法类型（ppo/sac/a2c）。"
            )
            raise ValueError(msg)

        algo_cls = algo_map[algorithm]
        model = algo_cls.load(model_path)
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

    def backtest(
        self,
        model_path: str,
        symbol: str,
        interval: str = "1h",
        lookback_days: int = 90,
    ) -> dict:
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
                    return Action(
                        action_type="buy",
                        confidence=0.8,
                        target_position=0.1,
                        model_id="rl_model",
                        inference_time_us=0,
                    )
                elif action_type == "sell" and self._position >= 0:
                    self._position = -0.1
                    return Action(
                        action_type="sell",
                        confidence=0.8,
                        target_position=0.0,
                        model_id="rl_model",
                        inference_time_us=0,
                    )
                elif action_type == "close_long" and self._position > 0:
                    self._position = 0.0
                    return Action(
                        action_type="sell",
                        confidence=0.9,
                        target_position=0.0,
                        model_id="rl_model",
                        inference_time_us=0,
                    )
                elif action_type == "close_short" and self._position < 0:
                    self._position = 0.0
                    return Action(
                        action_type="buy",
                        confidence=0.9,
                        target_position=0.0,
                        model_id="rl_model",
                        inference_time_us=0,
                    )

                return Action(
                    action_type="hold",
                    confidence=0.0,
                    target_position=0.0,
                    model_id="rl_model",
                    inference_time_us=0,
                )

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
            models.append(
                {
                    "name": f.stem,
                    "path": str(f),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                }
            )
        return sorted(models, key=lambda x: x["name"])

    def delete_model(self, model_name: str) -> bool:
        """删除模型（包括模型文件和元数据）

        Args:
            model_name: 模型名称（不含扩展名）

        Returns:
            True 如果删除成功，False 如果模型不存在
        """
        model_path = MODELS_DIR / f"{model_name}.zip"
        metadata_path = MODELS_DIR / f"{model_name}_metadata.json"

        if not model_path.exists():
            return False

        # 删除模型文件
        try:
            os.remove(model_path)
            logger.info(f"删除模型文件: {model_path}")
        except Exception as e:
            logger.error(f"删除模型文件失败: {e}")
            raise

        # 删除元数据文件（如果存在）
        if metadata_path.exists():
            try:
                os.remove(metadata_path)
                logger.info(f"删除元数据文件: {metadata_path}")
            except Exception as e:
                logger.warning(f"删除元数据文件失败: {e}")

        return True

    def _fetch_market_data(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        """获取市场数据（优先本地 parquet，fallback 到 Binance API），返回小写列名"""
        # 1. 尝试本地 parquet
        local_path = (
            Path(__file__).parent.parent
            / "data"
            / "source"
            / "crypto"
            / "spot"
            / "klines"
            / interval
            / f"{symbol}.parquet"
        )
        if local_path.exists():
            df = pd.read_parquet(local_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="us")
            df.set_index("timestamp", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = df[col].astype(float)
            logger.info(f"从本地加载 {len(df)} 根K线: {local_path}")
            return df[["open", "high", "low", "close", "volume"]]

        # 2. Fallback 到 Binance API
        limit = min(lookback_days * 96, 1000)  # 15min = 96根/天
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QuantCell/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            df = pd.DataFrame(
                data,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades",
                    "taker_buy_base",
                    "taker_buy_quote",
                    "ignore",
                ],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            return df[["open", "high", "low", "close", "volume"]]
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            raise

    def _df_to_env_data(self, df: pd.DataFrame) -> list[dict]:
        """将 DataFrame 转换为 TradingEnv 需要的 list[dict] 格式"""
        data = []
        for idx, row in df.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1e9) if not isinstance(idx, (int, float)) else int(idx)
            data.append(
                {
                    "timestamp": ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
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
                obs, reward, terminated, truncated, _info = env.step(action)
                total_reward += reward
                done = terminated or truncated
            rewards.append(total_reward)

        return {
            "eval_reward_mean": float(np.mean(rewards)),
            "eval_reward_std": float(np.std(rewards)),
        }
