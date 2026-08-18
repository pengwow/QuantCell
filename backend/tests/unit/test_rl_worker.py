"""Tests for worker/rl_worker.py — RLWorker."""

import numpy as np
import pytest

from worker.rl_worker import RLWorker


def _find_latest_model():
    """Find the latest .zip model in data/models/."""
    from pathlib import Path

    models_dir = Path(__file__).parent.parent.parent / "data" / "models"
    zips = sorted(models_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(zips[0]) if zips else None


MODEL_PATH = _find_latest_model()


@pytest.mark.skipif(MODEL_PATH is None, reason="No trained model found")
def test_rl_worker_creation():
    """RLWorker可以被创建"""
    worker = RLWorker(MODEL_PATH)
    assert worker._model is not None


@pytest.mark.skipif(MODEL_PATH is None, reason="No trained model found")
def test_rl_worker_predicts_action():
    """RLWorker能从observation预测交易动作"""
    worker = RLWorker(MODEL_PATH)
    obs = np.zeros(2, dtype=np.float32)
    result = worker.predict(obs)
    assert "side" in result
    assert result["side"] in ("buy", "sell", "hold")
    assert "raw_action" in result
    assert "confidence" in result
