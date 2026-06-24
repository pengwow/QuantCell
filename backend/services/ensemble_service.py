"""EnsembleService — axon_quant.ensemble wrapper."""

from __future__ import annotations

import uuid
from typing import Any

try:
    from axon_quant.ensemble import (
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


def _dummy_model(obs: dict[str, Any]) -> dict[str, Any]:
    """Placeholder model that returns hold."""
    return {"action_type": "hold", "confidence": 0.0, "quantity": 0.0}


class EnsembleService:
    """Ensemble service wrapping axon_quant.ensemble.EnsembleManager."""

    def __init__(self) -> None:
        if not AVAILABLE:
            raise RuntimeError("axon_quant.ensemble not available")
        self._ensembles: dict[str, EnsembleManager] = {}

    def create_ensemble(
        self,
        strategy: str = "soft_vote",
        model_paths: list[str] | None = None,
    ) -> str:
        """Create an ensemble and return its ID."""
        strategy_cls = _STRATEGY_MAP.get(strategy)
        if strategy_cls is None:
            raise ValueError(f"Unknown strategy: {strategy}")

        manager = EnsembleManager(strategy_cls())
        for i, _path in enumerate(model_paths or []):
            manager.register_model(_dummy_model, f"model_{i}", ModelType.RuleBased)

        eid = uuid.uuid4().hex[:8]
        self._ensembles[eid] = manager
        return eid

    def predict(
        self,
        ensemble_id: str,
        observation: dict[str, Any],
        timestamp: int = 0,
    ) -> dict[str, Any]:
        """Run ensemble prediction."""
        manager = self._ensembles.get(ensemble_id)
        if manager is None:
            raise KeyError(f"Ensemble {ensemble_id} not found")

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
        """List all ensembles."""
        return [
            {
                "id": eid,
                "models": m.model_count,
                "strategy": m.strategy_name,
            }
            for eid, m in self._ensembles.items()
        ]
