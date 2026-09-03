"""RL Worker — RL model inference for live trading.

Loads trained SB3 models (.zip) or ONNX models and generates trading signals.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class RLWorker:
    """RL model inference worker.

    Supports two model formats:
    - SB3 .zip files (native stable-baselines3 format)
    - ONNX files (via axon_quant.inference)

    Args:
        model_path: Path to the trained model file (.zip or .onnx).
    """

    def __init__(self, model_path: str):
        self._model_path = model_path
        self._model = None
        self._engine = None

        if model_path.endswith(".zip"):
            self._load_sb3(model_path)
        else:
            self._load_onnx(model_path)

    def _load_sb3(self, path: str):
        from stable_baselines3 import DQN, PPO, SAC

        algo_map = {"ppo": PPO, "sac": SAC, "dqn": DQN}
        for name, cls in algo_map.items():
            if name in path.lower():
                self._model = cls.load(path)
                logger.info(f"[RLWorker] 已加载 SB3 模型: {cls.__name__} from {path}")
                return
        self._model = PPO.load(path)
        logger.info(f"[RLWorker] 已加载 SB3 模型 (默认PPO): {path}")

    def _load_onnx(self, path: str):
        from axon_quant.inference import create_onnx_engine

        self._engine = create_onnx_engine(path)
        logger.info(f"[RLWorker] 已加载 ONNX 模型: {path}")

    def predict(self, observation: np.ndarray | dict[str, Any]) -> dict[str, Any]:
        """Predict trading action from observation.

        Args:
            observation: numpy array (Gymnasium obs) or dict with market features.

        Returns:
            Action dict with side (buy/sell/hold), quantity, confidence.
        """
        if self._model is not None:
            return self._predict_sb3(observation)
        return self._predict_onnx(observation)

    def _predict_sb3(self, observation) -> dict[str, Any]:
        if isinstance(observation, dict):
            obs = np.array(list(observation.values()), dtype=np.float32)
        else:
            obs = np.asarray(observation, dtype=np.float32)

        action, _ = self._model.predict(obs, deterministic=True)
        raw = float(action[0]) if hasattr(action, "__len__") else float(action)

        if raw > 0.05:
            side = "buy"
        elif raw < -0.05:
            side = "sell"
        else:
            side = "hold"

        return {
            "side": side,
            "quantity": abs(raw),
            "confidence": abs(raw),
            "raw_action": raw,
        }

    def _predict_onnx(self, observation) -> dict[str, Any]:
        action = self._engine.infer(observation)
        return {
            "side": "hold",
            "quantity": 0.0,
            "confidence": 0.0,
            "raw_action": action,
        }
