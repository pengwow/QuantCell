import os
import tempfile


def test_model_registry_service_creation():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        assert svc is not None


def test_model_registry_register_and_list():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        model_file = os.path.join(td, "test.onnx")
        with open(model_file, "wb") as f:
            f.write(b"dummy model")

        model_id = svc.register_model(
            name="test_ppo",
            model_path=model_file,
            metadata={"algorithm": "ppo", "timesteps": 10000},
            metrics={"sharpe": 1.5, "max_drawdown": 0.1},
        )
        assert model_id is not None

        models = svc.list_models()
        assert len(models) >= 1
        assert any(m["name"] == "test_ppo" for m in models)
