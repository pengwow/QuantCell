def test_ensemble_service_creation():
    from services.ensemble_service import EnsembleService

    svc = EnsembleService()
    assert svc is not None


def test_ensemble_service_create_and_predict():
    from services.ensemble_service import EnsembleService

    svc = EnsembleService()

    ensemble_id = svc.create_ensemble(
        strategy="soft_vote",
        model_paths=["/tmp/m1.onnx", "/tmp/m2.onnx"],
    )
    assert ensemble_id is not None

    result = svc.predict(ensemble_id, {"close": 50000.0, "volume": 1000.0})
    assert "action" in result
    assert "confidence" in result
