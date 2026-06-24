"""Tests for worker/ensemble_worker.py — EnsembleWorker."""


def test_ensemble_worker_creation():
    """EnsembleWorker可以被创建"""
    from worker.ensemble_worker import EnsembleWorker
    worker = EnsembleWorker(model_paths=["/tmp/m1.onnx", "/tmp/m2.onnx"], strategy="soft_vote")
    assert worker is not None


def test_ensemble_worker_predicts():
    """EnsembleWorker执行投票预测"""
    from worker.ensemble_worker import EnsembleWorker
    worker = EnsembleWorker(model_paths=["/tmp/m1.onnx", "/tmp/m2.onnx"], strategy="soft_vote")
    result = worker.predict({"close": 50000.0})
    assert "action" in result
    assert "confidence" in result
    assert "votes" in result
