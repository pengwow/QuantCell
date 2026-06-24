"""RL Worker — RL model inference for live trading.

Loads trained RL models and generates trading signals.
"""

from __future__ import annotations

from typing import Any

from axon_quant.inference import create_onnx_engine


class RLWorker:
    """RL model inference worker.

    Args:
        model_path: Path to the trained model file.
    """

    def __init__(self, model_path: str):
        self._model_path = model_path
        self._engine = create_onnx_engine(model_path)

    def predict(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Predict trading action from observation.

        Args:
            observation: Market observation dict with close, volume, position, etc.

        Returns:
            Action dict with side (buy/sell/hold), quantity, confidence.
        """
        action = self._engine.infer(observation)
        return {
            "side": "hold",
            "quantity": 0.0,
            "confidence": 0.0,
            "raw_action": action,
        }
