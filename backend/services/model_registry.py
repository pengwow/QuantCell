"""ModelRegistryService — axon_quant.registry wrapper."""

from __future__ import annotations

import json
from typing import Any

try:
    from axon_quant._native import registry as _registry_mod

    AVAILABLE = True
except ImportError:
    AVAILABLE = False


class ModelRegistryService:
    """Model registry service wrapping axon_quant ModelRegistry."""

    def __init__(self, storage_path: str = "data/models"):
        if not AVAILABLE:
            msg = "axon_quant.registry not available"
            raise RuntimeError(msg)
        import os

        persist_dir = os.path.join(storage_path, ".persist")
        os.makedirs(persist_dir, exist_ok=True)
        self._storage = _registry_mod.LocalStorage(storage_path)
        self._registry = _registry_mod.ModelRegistry(self._storage, persist_dir)

    def register_model(
        self,
        name: str,
        model_path: str,
        metadata: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> str:
        """Register a model and return its ID."""
        desc = json.dumps({"metadata": metadata or {}, "metrics": metrics or {}})
        result = self._registry.register(name, model_path, desc)
        return result["version"]

    def list_models(self) -> list[dict[str, Any]]:
        """List all registered models."""
        names = self._registry.list_models()
        return [{"name": n} for n in names]

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        """Get production model by name."""
        try:
            return self._registry.get_production(model_id)
        except Exception:
            return None

    def promote_to_production(self, model_id: str) -> bool:
        """Promote latest version of a model to production."""
        names = self._registry.list_models()
        if model_id not in names:
            return False
        prod = self._registry.get_production(model_id)
        version = prod.get("version", "1.0.0") if prod else "1.0.0"
        self._registry.promote_to_production(model_id, version)
        return True
