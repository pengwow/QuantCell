"""EnsembleService — axon_quant.ensemble wrapper。"""

from __future__ import annotations

import pickle
import uuid
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable


# ponytail: 限制 pickle 反序列化范围，防止任意代码执行
class _SafeUnpickler(pickle.Unpickler):
    _ALLOWED_PREFIXES = ("sklearn.", "numpy.", "builtins.", "collections.", "datetime.")

    def find_class(self, module: str, name: str):
        if not any(module.startswith(p) for p in self._ALLOWED_PREFIXES):
            msg = f"不允许的类型: {module}.{name}"
            raise pickle.UnpicklingError(msg)
        return super().find_class(module, name)


try:
    from axon_bridge import (
        Action,
        ActionType,
        EnsembleManager,
        HardVoteStrategy,
        ModelType,
        Observation,
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


def _load_model_from_path(path: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """从 pickle 文件加载模型并包装为 ensemble 兼容的 callable。

    返回的 callable 接收 Observation-like dict，返回 {"action_type": str, "confidence": float}。
    支持：sklearn 风格 .predict()、callable 模型。
    """
    p = Path(path)
    if not p.exists():
        msg = f"模型文件不存在: {path}"
        raise FileNotFoundError(msg)
    with open(p, "rb") as f:
        model = _SafeUnpickler(f).load()

    def _predict(obs: dict[str, Any]) -> dict[str, Any]:
        # 拼接所有特征为一维向量
        features = []
        for key in ("market_features", "technical_indicators", "time_features"):
            val = obs.get(key, [])
            features.extend(val if isinstance(val, list) else [])
        x = np.array(features, dtype=float).reshape(1, -1)

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

        # 简单映射：0=hold, 1=buy, 2=sell
        action_map = {0: "hold", 1: "buy", 2: "sell"}
        return {
            "action_type": action_map.get(action_idx, "hold"),
            "confidence": confidence,
        }

    return _predict


class EnsembleService:
    """Ensemble service wrapping axon_quant.ensemble.EnsembleManager。"""

    def __init__(self) -> None:
        if not AVAILABLE:
            msg = "axon_quant.ensemble not available"
            raise RuntimeError(msg)
        self._ensembles: dict[str, EnsembleManager] = {}

    def create_ensemble(
        self,
        strategy: str = "soft_vote",
        model_paths: list[str] | None = None,
    ) -> str:
        """创建集成并返回 ID。model_paths 为 pickle 模型文件路径列表。"""
        strategy_cls = _STRATEGY_MAP.get(strategy)
        if strategy_cls is None:
            msg = f"Unknown strategy: {strategy}"
            raise ValueError(msg)

        manager = EnsembleManager(strategy_cls())
        for i, path in enumerate(model_paths or []):
            try:
                model_fn = _load_model_from_path(path)
                manager.register_model(model_fn, f"model_{i}", ModelType.RuleBased)
            except Exception as e:
                from utils.logger import LogType, get_logger

                logger = get_logger(__name__, LogType.APPLICATION)
                logger.warning(f"加载模型 {path} 失败: {e}，跳过")

        eid = uuid.uuid4().hex[:8]
        self._ensembles[eid] = manager
        return eid

    def predict(
        self,
        ensemble_id: str,
        observation: dict[str, Any],
        timestamp: int = 0,
    ) -> dict[str, Any]:
        """运行集成预测。"""
        manager = self._ensembles.get(ensemble_id)
        if manager is None:
            msg = f"Ensemble {ensemble_id} not found"
            raise KeyError(msg)

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
        return {
            "action": result.action_type,
            "confidence": float(result.confidence),
        }

    def list_ensembles(self) -> list[dict[str, Any]]:
        """列出所有集成。"""
        return [
            {
                "id": eid,
                "models": m.model_count,
                "strategy": m.strategy_name,
            }
            for eid, m in self._ensembles.items()
        ]


@lru_cache(maxsize=1)
def get_ensemble_service() -> EnsembleService:
    """模块级单例。"""
    return EnsembleService()
