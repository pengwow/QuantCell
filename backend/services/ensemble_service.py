"""EnsembleService — axon_quant.ensemble wrapper。"""

from __future__ import annotations

import json
import pickle
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from services.rl_service import MODELS_DIR  # 单一事实源,严禁在本模块重新定义(spec §8)
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__, LogType.APPLICATION)

# 集成元数据落盘:与 MODELS_DIR 同级(backend/data/ensembles.json)
ENSEMBLES_STORE = MODELS_DIR.parent / "ensembles.json"


# ponytail: 限制 pickle 反序列化范围，防止任意代码执行
class _SafeUnpickler(pickle.Unpickler):
    _ALLOWED_PREFIXES = ("sklearn.", "numpy.", "builtins.", "collections.", "datetime.")

    def find_class(self, module: str, name: str):
        # 顶层类(如 numpy.dtype)的 module 恰为 "numpy" 不带点,prefix 匹配会误杀,
        # 需同时放行「模块名完全相等」与「模块名前缀匹配」两种情形
        if not any(module == p.rstrip(".") or module.startswith(p) for p in self._ALLOWED_PREFIXES):
            msg = f"不允许的类型: {module}.{name}"
            raise pickle.UnpicklingError(msg)
        return super().find_class(module, name)


try:
    from axon_quant.ensemble import Observation  # ensemble 专用 Observation, 与根级版本不同

    from axon_bridge import (
        Action,
        ActionType,
        EnsembleManager,
        HardVoteStrategy,
        ModelType,
        SoftVoteStrategy,
        WeightedVoteStrategy,
    )

    AVAILABLE = True
except ImportError:
    AVAILABLE = False

_STRATEGY_MAP = {
    "soft_vote": SoftVoteStrategy if AVAILABLE else None,
    "hard_vote": HardVoteStrategy if AVAILABLE else None,
    "weighted": WeightedVoteStrategy if AVAILABLE else None,
}


class _UnsupportedActionSpace(ValueError):
    """连续动作模型(Box 输出)不能参与离散投票;create 阶段需整体拒绝而非跳过。"""


# 0=hold, 1=buy, 2=sell —— pickle 与 SB3 两条加载分支共用
_ACTION_MAP = {0: "hold", 1: "buy", 2: "sell"}


def _features_from_obs(obs: Any) -> np.ndarray:
    """从 Observation(Rust pyclass,属性访问)或 dict(.get)统一提取特征并拼成一维向量。

    EnsembleManager 传给注册 callable 的形态不在类型上约束,两种访问方式都兼容。
    """
    getter = obs.get if hasattr(obs, "get") else (lambda k, d=None: getattr(obs, k, d))
    features: list[float] = []
    for key in ("market_features", "technical_indicators", "time_features"):
        val = getter(key, [])
        if isinstance(val, (list, tuple)):
            features.extend(val)
        elif val is not None:
            features.append(float(val))
    return np.array(features, dtype=float).reshape(1, -1)


def _resolve_sb3_zip(entry: str) -> Path | None:
    """判断输入是否指向 SB3 zip:裸 stem(无路径分隔符)或 {stem}.zip,
    且 MODELS_DIR 下存在同名 zip 时返回该路径;否则 None 走 pickle 分支。
    """
    if "/" in entry or "\\" in entry:
        return None
    stem = Path(entry).stem if entry.endswith(".zip") else entry
    zip_path = MODELS_DIR / f"{stem}.zip"
    return zip_path if zip_path.exists() else None


def _load_sb3_model(zip_path: Path) -> Callable[[Any], dict[str, Any]]:
    """加载 MODELS_DIR 下的 SB3 zip 并包装为 ensemble 兼容的 callable。

    算法按文件名关键词选择(对齐 rl_service.load_model 既有写法),未知关键词回退 PPO。
    连续动作空间(SAC/TD3 等 Box 输出)抛 _UnsupportedActionSpace,由 create 整体拒绝。
    """
    # 函数内 import:torch/SB3/gymnasium 加载重,仅 SB3 分支真正用到时才引入
    from gymnasium import spaces
    from stable_baselines3 import A2C, DQN, PPO, SAC

    stem = zip_path.stem.lower()
    if "sac" in stem:
        cls = SAC
    elif "dqn" in stem:
        cls = DQN
    elif "a2c" in stem:
        cls = A2C
    else:
        cls = PPO

    model = cls.load(str(zip_path))
    if not isinstance(model.action_space, spaces.Discrete):
        raise _UnsupportedActionSpace(f"连续动作模型暂不支持集成投票: {zip_path.stem}")

    def _predict(obs: Any) -> dict[str, Any]:
        x = _features_from_obs(obs)
        action, _ = model.predict(x, deterministic=True)
        action_idx = int(np.asarray(action).reshape(-1)[0])
        # ponytail: Discrete 模型无概率输出,confidence 固定 0.8;升级路径 = policy 输出概率distribution
        return {"action_type": _ACTION_MAP.get(action_idx, "hold"), "confidence": 0.8}

    return _predict


def _load_model_from_path(path: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """按输入语义二态加载模型并包装为 ensemble 兼容的 callable(spec §5.1)。

    - 裸 stem 或 {stem}.zip → 解析到 MODELS_DIR/{stem}.zip 的 SB3 模型
    - 其余(带路径分隔符)→ sklearn pickle 白名单加载,行为不变
    返回的 callable 接收 Observation-like dict,返回 {"action_type": str, "confidence": float}。
    """
    resolved = _resolve_sb3_zip(path)
    if resolved is not None:
        return _load_sb3_model(resolved)

    p = Path(path)
    if not p.exists():
        msg = f"模型文件不存在: {path}"
        raise FileNotFoundError(msg)
    with open(p, "rb") as f:
        model = _SafeUnpickler(f).load()

    def _predict(obs: dict[str, Any]) -> dict[str, Any]:
        x = _features_from_obs(obs)

        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(x)[0]
            action_idx = int(np.argmax(probs))
            confidence = float(np.max(probs))
        elif hasattr(model, "predict"):
            pred = model.predict(x)[0]
            action_idx = int(pred) if hasattr(pred, "__int__") else 0
            confidence = 0.8
        elif callable(model):
            result = model(obs)
            if isinstance(result, dict):
                return result
            action_idx = int(result) if hasattr(result, "__int__") else 0
            confidence = 0.8
        else:
            msg = f"不支持的模型类型: {type(model)}"
            raise TypeError(msg)

        return {"action_type": _ACTION_MAP.get(action_idx, "hold"), "confidence": confidence}

    return _predict


class EnsembleService:
    """Ensemble service wrapping axon_quant.ensemble.EnsembleManager。

    元数据(records)持久化于 ENSEMBLES_STORE,manager 内存实例惰性重建:
    只有 create 与首次 predict 需要真实加载模型,启动时零加载。
    """

    def __init__(self) -> None:
        if not AVAILABLE:
            msg = "axon_quant.ensemble not available"
            raise RuntimeError(msg)
        self._managers: dict[str, EnsembleManager] = {}
        self._records: dict[str, dict[str, Any]] = self._load_records()

    # ---- 元数据持久化 ----

    def _load_records(self) -> dict[str, dict[str, Any]]:
        if not ENSEMBLES_STORE.exists():
            return {}
        try:
            raw = json.loads(ENSEMBLES_STORE.read_text(encoding="utf-8"))
            return {r["id"]: r for r in raw}
        except (json.JSONDecodeError, KeyError, OSError, TypeError) as e:
            logger.warning(f"集成元数据读取失败,按空列表启动: {e}")
            return {}

    def _save_records(self) -> None:
        """原子写(临时文件 + replace),避免半写损坏。"""
        tmp = ENSEMBLES_STORE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(list(self._records.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(ENSEMBLES_STORE)

    # ---- 对外接口 ----

    def create_ensemble(
        self,
        strategy: str = "soft_vote",
        model_paths: list[str] | None = None,
    ) -> tuple[str, list[dict[str, str]]]:
        """创建集成,返回 (ensemble_id, 加载失败被跳过的模型列表)。

        model_paths 语义:裸 stem(→ MODELS_DIR 下 SB3 zip)或绝对路径(pickle)。
        连续动作模型抛 _UnsupportedActionSpace 整单拒绝;单个文件加载失败只跳过。
        """
        strategy_cls = _STRATEGY_MAP.get(strategy)
        if strategy_cls is None:
            msg = f"Unknown strategy: {strategy}"
            raise ValueError(msg)

        manager = EnsembleManager(strategy_cls())
        loaded = 0
        skipped: list[dict[str, str]] = []
        for i, path in enumerate(model_paths or []):
            try:
                model_fn = _load_model_from_path(path)
                manager.register_model(model_fn, f"model_{i}", ModelType.RuleBased)
                loaded += 1
            except _UnsupportedActionSpace:
                raise
            except Exception as e:
                logger.warning(f"加载模型 {path} 失败: {e}，跳过")
                skipped.append({"path": path, "reason": str(e)})

        eid = uuid.uuid4().hex[:8]
        self._records[eid] = {
            "id": eid,
            "strategy": strategy,
            "model_paths": list(model_paths or []),
            "models": loaded,  # 创建时成功加载的数量,重启后 list 直接读记录
            "created_at": int(time.time()),
        }
        self._managers[eid] = manager
        self._save_records()
        return eid, skipped

    def delete_ensemble(self, ensemble_id: str) -> None:
        """删除集成(内存与磁盘元数据同步)。id 不存在抛 KeyError。"""
        if ensemble_id not in self._records:
            msg = f"Ensemble {ensemble_id} not found"
            raise KeyError(msg)
        self._records.pop(ensemble_id, None)
        self._managers.pop(ensemble_id, None)
        self._save_records()

    def predict(
        self,
        ensemble_id: str,
        observation: dict[str, Any],
        timestamp: int = 0,
    ) -> dict[str, Any]:
        """运行集成预测。manager 不在内存时从元数据惰性重建。"""
        manager = self._managers.get(ensemble_id)
        if manager is None:
            manager = self._rebuild_manager(ensemble_id)
            self._managers[ensemble_id] = manager

        if "market_features" in observation:
            obs = Observation(
                market_features=list(observation["market_features"]),
                technical_indicators=list(observation.get("technical_indicators", [])),
                time_features=list(observation.get("time_features", [])),
            )
        else:
            obs = Observation(
                market_features=list(observation.values()),
                technical_indicators=[],
                time_features=[],
            )
        result = manager.predict(obs, timestamp)
        # action_type 是 Rust 侧 pyclass 枚举(无 __hash__,pydantic 也无法 JSON 序列化),统一转小写字符串
        return {
            "action": str(result.action_type),
            "confidence": float(result.confidence),
        }

    def list_ensembles(self) -> list[dict[str, Any]]:
        """列出所有集成(读元数据;models 为创建时成功加载的数量)。"""
        return [dict(r) for r in self._records.values()]

    # ---- 内部 ----

    def _rebuild_manager(self, ensemble_id: str) -> EnsembleManager:
        """重启后首次 predict 时按元数据重建 manager。"""
        record = self._records.get(ensemble_id)
        if record is None:
            msg = f"Ensemble {ensemble_id} not found"
            raise KeyError(msg)
        strategy_cls = _STRATEGY_MAP.get(record["strategy"])
        if strategy_cls is None:
            msg = f"Unknown strategy: {record['strategy']}"
            raise ValueError(msg)
        manager = EnsembleManager(strategy_cls())
        for i, path in enumerate(record.get("model_paths", [])):
            try:
                manager.register_model(_load_model_from_path(path), f"model_{i}", ModelType.RuleBased)
            except Exception as e:
                logger.warning(f"重建集成 {ensemble_id} 时加载模型 {path} 失败: {e}，跳过")
        return manager


@lru_cache(maxsize=1)
def get_ensemble_service() -> EnsembleService:
    """模块级单例。"""
    return EnsembleService()
