"""RL Training Pipeline Service.

Unified entry point for RL training, HPO, Walk-Forward, and model registry.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from axon_quant.rl import run_kernel_backtest

from backtest.hpo_runner import HPORunner
from backtest.walk_forward import WalkForwardService
from services.ensemble_aggregator import make_ensemble_predict_fn
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    import pandas as pd

logger = get_logger(__name__, LogType.APPLICATION)

MODELS_DIR = Path(__file__).parent.parent / "data" / "models"

# 内核 RL 口径：与训练环境 `PyTradingEnv` 的默认观测空间一致
# （close Z-Score + volume 不归一化，window=1），保证模型输入维度对齐。
#
# 训练期观测归一化统计量（RunningStats）随模型落盘：训练结束时写进
# `<model>.meta.json` 的 `observation_stats`，内核路径用 `stats=` 灌回，
# 让内核侧 Z-Score 与训练分布一致。meta 缺该字段时内核统计量全空（Z-Score
# 恒为 0），加载处会告警 —— 那种情况下内核结果不能当作与训练等价的评估口径。
KERNEL_SPEC_VERSION = "v1"
KERNEL_WINDOW_SIZE = 1
KERNEL_FEATURES = [
    {"name": "close", "source": {"PriceField": "close"}, "normalizer": "ZScore", "clip_range": None},
    {"name": "volume", "source": {"VolumeField": "volume"}, "normalizer": "None", "clip_range": None},
]
# 内核 RL host 的动作空间必须是覆盖 [-1, 1] 的连续空间，
# 这样 `ratio -> Action -> decode_target_ratio` 才是恒等映射
KERNEL_ACTION_SPACE = {"type": "continuous", "min": -1.0, "max": 1.0}

# RL 成本口径的唯一来源：训练环境（`TradingEnv`）与内核评估（`worker.Kernel`）
# 都从这里取，改这一处即两边同步。任何一边自己写数字都会让
# `attribute_engine_diff` 报「成本模型不一致」。
RL_TRANSACTION_COST = 0.0001
RL_SLIPPAGE = 0.00001


def rl_meta_path(model_path: str) -> Path:
    """模型观测规格元数据旁车文件路径（训练时写入，启动时校验口径）。"""
    return Path(f"{model_path}.meta.json")


def export_observation_stats(env: Any) -> list[dict[str, Any]] | None:
    """从训练环境导出观测归一化统计量（写进模型旁车用）。

    `TradingEnv.observation_stats()` 返回 JSON 字符串（`"null"` 表示没有归一化
    状态）。这里直接落成 JSON 数组，读侧不用再 parse 一遍字符串。

    取不到统计量时返回 `None` 并告警，交给 meta 写成 `null`：埋一个假的空统计量
    比明说「没有」更危险。
    """
    getter = getattr(env, "observation_stats", None)
    if getter is None:
        logger.warning("[RLService] 训练环境没有 observation_stats()，模型元数据将不含归一化统计量")
        return None
    raw = getter()
    stats = json.loads(raw) if isinstance(raw, str) else raw
    if not stats:
        logger.warning("[RLService] 训练环境未产生归一化统计量，模型元数据 observation_stats 记为 null")
        return None
    # 条目全为 count=0 说明训练期从未预热（统计量信息量等于空），
    # 落成 null 比存一串假的 0 更有辨识度
    if all(not entry.get("count") for entry in stats):
        logger.warning("[RLService] 观测统计量全未预热（count=0），模型元数据 observation_stats 记为 null")
        return None
    return stats


def observation_stats_from_meta(meta: dict[str, Any], *, model_path: str) -> list[dict[str, Any]] | None:
    """从模型旁车元数据取观测归一化统计量。

    缺字段返回 `None` 并告警：内核侧统计量全空会让 Z-Score 恒为 0，特征分布与
    训练时不一致，不能静默当成「等价口径」。
    """
    stats = meta.get("observation_stats")
    if not stats:
        logger.warning(
            f"[RLService] {rl_meta_path(model_path)} 缺少 observation_stats，内核侧 Z-Score 恒为 0，与训练分布不一致"
        )
        return None
    return stats


def load_observation_stats(model_path: str) -> list[dict[str, Any]] | None:
    """读模型旁车里的观测归一化统计量（回测 / 推理侧灌回内核用）。"""
    meta_file = rl_meta_path(model_path)
    if not meta_file.is_file():
        logger.warning(f"[RLService] RL 模型缺少观测规格元数据，内核统计量全空: {meta_file}")
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    return observation_stats_from_meta(meta, model_path=model_path)


def attribute_engine_diff(*, trading_env: dict[str, Any], kernel: dict[str, Any]) -> dict[str, Any]:
    """把两口径的收益差异拆成 成本 / 资金费 / 动作 / 撮合 四类。

    前提：两次运行使用同一动作序列（确定性策略）。**成本类比较的是费率口径
    （`fees / turnover`），不是绝对手续费**：两边成交笔数不同（内核逐 bar 重平衡、
    `TradingEnv` 有最小成交阈值）时绝对手续费必然不同，那属于「撮合」差异，
    不是成本模型不一致。费率不同才是 bug。

    输入是两次运行的汇总，两边同形、缺省为 0：

    - `total_pnl`：净收益，已扣成本、已加资金费；
    - `fees`：累计交易成本（正数 = 支出）；
    - `turnover`：成交名义总额（Σ|price×qty|），`cost` 用它把手续费折算成费率；
      缺失或为 0 时该侧费率记 0；
    - `funding`：累计资金费净额（正数 = 收入）；`TradingEnv` 不建模资金费，恒为 0；
    - `action_diff`：可选，由调用方单独测得的「目标仓位语义」收益贡献。

    口径：`net = gross - fees + funding`，因此

        total_diff = -fees_diff + funding + action_diff + 残差

    残差（`matching.residual`）来自撮合层：成交价、部分成交、保证金约束、重平衡
    阈值等。**不假装能把残差再拆细** —— 要细分就得逐笔成交对齐，那不在本函数的
    口径内；宁可把「说不清的部分」整体挂在 `matching` 上。

    Args:
        trading_env: `TradingEnv` 口径的汇总。
        kernel: 统一内核口径的汇总。

    Returns:
        `cost` / `funding` / `action` / `matching` / `total_pnl` 五类归因；
        两侧费率不一致时额外带 `error`。
    """
    env_pnl = float(trading_env.get("total_pnl", 0.0))
    kernel_pnl = float(kernel.get("total_pnl", 0.0))
    env_fees = float(trading_env.get("fees", 0.0))
    kernel_fees = float(kernel.get("fees", 0.0))

    # 费率 = 手续费 / 成交名义。turnover 缺失或为 0 时没有可比较的费率，记 0
    env_turnover = float(trading_env.get("turnover") or 0.0)
    kernel_turnover = float(kernel.get("turnover") or 0.0)
    env_rate = env_fees / env_turnover if env_turnover > 0.0 else 0.0
    kernel_rate = kernel_fees / kernel_turnover if kernel_turnover > 0.0 else 0.0
    rate_diff = kernel_rate - env_rate
    # 费率是浮点除法，按 1e-12 绝对容差判等（0.0001 量级的相对误差 ~1e-8 以内）
    rate_ok = abs(rate_diff) <= 1e-12

    # 残差口径不变：仍用绝对手续费把两边 net 拉回 gross
    fees_diff = kernel_fees - env_fees
    funding = float(kernel.get("funding", 0.0))
    action_diff = float(kernel.get("action_diff", 0.0)) - float(trading_env.get("action_diff", 0.0))
    total_diff = kernel_pnl - env_pnl
    # net = gross - fees + funding ⇒ 残差 = 总差 + 手续费差 - 资金费 - 动作差
    residual = total_diff + fees_diff - funding - action_diff

    report: dict[str, Any] = {
        "cost": {
            "trading_env_rate": env_rate,
            "kernel_rate": kernel_rate,
            "diff": rate_diff,
            "ok": rate_ok,
        },
        "funding": {"kernel": funding},
        "action": {"diff": action_diff},
        "matching": {"residual": residual},
        "total_pnl": {"trading_env": env_pnl, "kernel": kernel_pnl, "diff": total_diff},
    }
    if not rate_ok:
        report["error"] = "成本模型不一致"
    return report


def make_predict_fn(model: Any):
    """把 SB3 模型包装成内核 RL host 需要的 `obs -> target_ratio` 回调。

    训练时用的是 `GymnasiumWrapper` 的 `Box(0, 1)` 动作空间（只做多），
    因此这里把模型输出裁剪到 `[0, 1]`；内核侧动作空间仍是 `[-1, 1]`，正值直接透传。
    """

    def predict(obs: list[float]) -> float:
        action, _ = model.predict(np.asarray(obs, dtype=np.float32), deterministic=True)
        return float(np.clip(np.asarray(action, dtype=np.float64).reshape(-1)[0], 0.0, 1.0))

    return predict


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
        "transaction_cost": RL_TRANSACTION_COST,
        "slippage": RL_SLIPPAGE,
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
        initial_capital: float = 100_000.0,
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
        config = _make_env_config(initial_capital=initial_capital, max_steps=len(df))
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

        # 统计量必须在训练循环跑完后再取：每次 step 都会在线更新 RunningStats
        observation_stats = export_observation_stats(env)

        model_id = f"{config.model_name}_{config.algorithm}_{int(time.time())}"
        model_path = str(MODELS_DIR / f"{model_id}.zip")
        model.save(model_path)

        # elapsed 计算前移到 meta 写入之前:elapsed_seconds 要随训练上下文落盘
        elapsed = time.time() - start_time

        # 观测规格元数据:RL 策略启动时据此校验 spec_version / 窗口 / 特征是否
        # 与本机内核口径一致,避免拿旧口径模型去跑新内核;
        # algorithm/total_timesteps/elapsed_seconds/reward_type/created_at/
        # walk_forward 是模型卡的训练上下文,注册表 seed 时并入 metadata
        rl_meta_path(model_path).write_text(
            json.dumps(
                {
                    "model_id": model_id,
                    "spec_version": KERNEL_SPEC_VERSION,
                    "window_size": KERNEL_WINDOW_SIZE,
                    "features": KERNEL_FEATURES,
                    # 训练期归一化统计量:内核路径据此还原 Z-Score 分布,
                    # 取不到时写 null(不伪造空统计量)
                    "observation_stats": observation_stats,
                    "algorithm": config.algorithm,
                    "total_timesteps": config.total_timesteps,
                    "elapsed_seconds": round(elapsed, 2),
                    "reward_type": config.reward_type,
                    # ISO 8601 毫秒精度(项目时间戳规范)
                    "created_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    # walk-forward 完整结果(OOS 折明细 + 汇总);seed 并入注册表时只取 aggregate
                    "walk_forward": wf_result,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.info(f"[RLService] 模型已保存: {model_path}")

        wrapped_env.close()

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

    def delete_saved_model(self, model_id: str) -> None:
        """删除指定模型文件（文件即模型存在的唯一事实）。

        ponytail: Rust registry（model_registry）无 delete API，注册条目删除后
        会成为孤立记录；列表展示一律以 MODELS_DIR 下 .zip 文件为准，孤立条目
        无副作用。若未来 Rust 侧补 delete，再在此同步调用。
        """
        # 白名单字符集杜绝路径分隔符；`.`/`..` 虽过正则但无业务意义，显式排除；
        # resolve 后再校验父目录双保险，防止 Windows 保留名 / 软链接等绕过正则
        if model_id in {".", ".."} or not re.fullmatch(r"[\w.\-]+", model_id or ""):
            raise ValueError(f"非法的模型 ID: {model_id!r}")
        target = (MODELS_DIR / f"{model_id}.zip").resolve()
        if target.parent != MODELS_DIR.resolve():
            raise ValueError(f"非法的模型路径: {model_id!r}")
        if not target.is_file():
            raise FileNotFoundError(f"模型不存在: {model_id}")
        target.unlink()
        # 观测规格旁车文件一并清理，避免残留陈旧 meta
        with contextlib.suppress(FileNotFoundError):
            rl_meta_path(str(target)).unlink()
        logger.info(f"[RLService] 模型已删除: {model_id}")

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
        engine: str = "trading_env",
        ensemble_id: str | None = None,
    ) -> dict[str, Any]:
        """用已训练模型回测，返回评估指标。

        Args:
            engine: 评估口径。
                - `"trading_env"`（默认）：SB3 + `axon_quant TradingEnv` 逐 step 评估；
                - `"kernel"`：统一内核 `worker.Kernel` + RL host，撮合与实盘同一主回路。
            ensemble_id: 非空时按模型集成加载成员（Python 侧聚合），仅 engine="kernel"
                有效，此时 `model_path` 忽略。
            响应体固定带 `engine` 字段，调用方据此区分两条口径。

        Uses TradingEnv as the simulation engine and the SB3 model for inference.
        Returns evaluation metrics (PnL, Sharpe, drawdown, etc.).
        """
        # backtest.data_provider 顶层 import pandas 栈；保持调用点导入，
        # rl_service 被轻量场景引用时（测试收集 / CLI）不为此拉起数据链路
        from backtest.data_provider import BacktestDataProvider

        if engine not in ("trading_env", "kernel"):
            msg = f"未知 engine: {engine}（可选 'trading_env' / 'kernel'）"
            raise ValueError(msg)

        if ensemble_id and engine != "kernel":
            msg = "ensemble_id 仅支持 kernel 引擎回测(trading_env 口径按单模型加载)"
            raise ValueError(msg)

        provider = BacktestDataProvider()
        data = provider.load_klines(symbol, interval, candle_type)
        if data.empty:
            msg = f"无法加载 {symbol} {interval} 数据"
            raise ValueError(msg)

        if engine == "kernel":
            return self._run_kernel_backtest(
                model_path, data, symbol, interval, initial_capital, ensemble_id=ensemble_id
            )

        # 不能提升到模块顶部：rl/__init__ 反向 import 本模块（GymnasiumWrapper 等），
        # rl_service 模块期 import rl.* 会撞上半初始化的 rl 包成环
        from rl.evaluation import evaluate_model

        env = self.create_env(data, reward_type=reward_type, initial_capital=initial_capital)
        wrapped_env = GymnasiumWrapper(env)

        model = self.load_model(model_path)
        if model is None:
            msg = f"无法加载模型: {model_path}"
            raise RuntimeError(msg)

        metrics = evaluate_model(model, wrapped_env, transaction_cost=RL_TRANSACTION_COST)
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
            # 成交名义总额：`attribute_engine_diff` 用它把手续费折算成费率口径
            "turnover": metrics.turnover,
            "engine": "trading_env",
        }

    def _run_kernel_backtest(
        self,
        model_path: str,
        data: pd.DataFrame,
        symbol: str,
        interval: str,
        initial_capital: float,
        ensemble_id: str | None = None,
    ) -> dict[str, Any]:
        """统一内核路径：backend 编排（模型 IO / 数据清洗 / symbol 归一化）→ 执行设施。

        执行段（worker.Kernel 装配 + 15 字段结果拼装）已下沉
        `axon_quant.rl.kernel_backtest::run_kernel_backtest`（2026-11-11），
        与 `trading_env` 口径的差别只在编排层：成交、资金费、保证金与统计
        全部由 Rust 内核完成（与实盘同一条主回路）。`ensemble_id` 非空时走
        集成员聚合，不再加载单模型。
        """
        from backtest.backtest_loop import clean_ohlcv_df
        from backtest.engine_service import EventDrivenBacktestService
        from strategy.rust_adapter import _normalize_symbol

        if ensemble_id:
            # 集成:成员 ratio predict_fn 组合,spec 以基准成员 meta 为准(spec §4.4)
            # 函数内 import:ensemble_service 顶层依赖本模块(rl_service),顶部 import 会成环
            from services.ensemble_service import load_ensemble_spec

            member_specs = load_ensemble_spec(ensemble_id, spec_version=KERNEL_SPEC_VERSION)
            predict_fn = make_ensemble_predict_fn(member_specs.member_predict_fns)
            model_id = ensemble_id
            window_size = int(member_specs.meta.get("window_size") or KERNEL_WINDOW_SIZE)
            features = member_specs.meta.get("features") or KERNEL_FEATURES
            stats = observation_stats_from_meta(member_specs.meta, model_path=member_specs.representative_path)
        else:
            model = self.load_model(model_path)
            if model is None:
                msg = f"无法加载模型: {model_path}"
                raise RuntimeError(msg)
            predict_fn = make_predict_fn(model)
            model_id = Path(model_path).stem
            window_size = KERNEL_WINDOW_SIZE
            features = KERNEL_FEATURES
            stats = load_observation_stats(model_path)

        # 内核按 BASE/QUOTE 建 instrument；直接用交易所原始 symbol 会退化成默认品种
        rust_symbol = _normalize_symbol(symbol)
        bars = EventDrivenBacktestService._df_to_rust_bars(clean_ohlcv_df(data))

        # 费率与训练环境同源：两边都是 `RL_TRANSACTION_COST`，否则归因会报成本模型不一致
        result = run_kernel_backtest(
            bars,
            predict_fn,
            rust_symbol,
            interval,
            {
                "spec_version": KERNEL_SPEC_VERSION,
                "window_size": window_size,
                "features": features,
                "action_space": KERNEL_ACTION_SPACE,
            },
            initial_capital=initial_capital,
            fee_rate=RL_TRANSACTION_COST,
            stats=stats,
            model_id=model_id,
        )
        # 设施回显内核 symbol 与 len(bars)；对外契约沿用原始 symbol 与清洗前行数
        result["symbol"] = symbol
        result["data_bars"] = len(data)
        return result
