import json
import os
import tempfile

import pytest


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


def _make_demo_artifact(td: str, model_id: str) -> str:
    """造一个训练产物 zip + .meta.json,模拟 rl_service 的落盘方式"""
    zip_path = os.path.join(td, f"{model_id}.zip")
    with open(zip_path, "wb") as f:
        f.write(b"dummy sb3 model")
    with open(zip_path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "model_id": model_id,
                "spec_version": "v1",
                "window_size": 1,
                "features": [{"name": "close"}, {"name": "volume"}],
            },
            f,
        )
    return zip_path


def test_seed_demo_models_registers_and_promotes_first():
    from services.model_registry import ModelRegistryService, seed_demo_models

    with tempfile.TemporaryDirectory() as td:
        for i in range(3):
            _make_demo_artifact(td, f"rl_model_ppo_170000000{i}")

        registered = seed_demo_models(storage_path=td)
        assert len(registered) == 3

        svc_rows = ModelRegistryService(storage_path=td).list_models()
        names = [r["name"] for r in svc_rows]
        assert len(names) == 3
        stages = {r["name"]: r["stage"] for r in svc_rows}
        # 第一个注册的被晋升为 production,其余保持 development
        assert list(stages.values()).count("production") == 1
        assert list(stages.values()).count("development") == 2
        prod_row = next(r for r in svc_rows if r["stage"] == "production")
        assert prod_row["version"]


def test_seed_demo_models_idempotent_when_registry_not_empty():
    from services.model_registry import seed_demo_models

    with tempfile.TemporaryDirectory() as td:
        _make_demo_artifact(td, "rl_model_ppo_1700000000")
        assert len(seed_demo_models(storage_path=td)) == 1
        # 第二次(seed 内部先查 list_models 非空即跳过)
        assert seed_demo_models(storage_path=td) == []


def test_seed_demo_models_tolerates_empty_dir():
    from services.model_registry import seed_demo_models

    with tempfile.TemporaryDirectory() as td:
        assert seed_demo_models(storage_path=td) == []


def test_list_models_returns_full_contract():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        model_file = os.path.join(td, "test.onnx")
        with open(model_file, "wb") as f:
            f.write(b"dummy")
        svc.register_model(name="contract_model", model_path=model_file, metrics={"sharpe": 1.5})

        row = svc.list_models()[0]
        assert set(row.keys()) == {"id", "name", "version", "stage", "metrics"}
        assert row["id"] == row["name"] == "contract_model"
        assert row["stage"] == "development"
        assert row["version"] == ""
        assert row["metrics"] == {}


def test_promote_no_production_then_noop():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        model_file = os.path.join(td, "test.onnx")
        with open(model_file, "wb") as f:
            f.write(b"dummy")
        svc.register_model(name="prom_model", model_path=model_file)

        assert svc.promote_to_production("prom_model") is True
        assert svc.get_model("prom_model")["stage"] == "production"
        # 已是 Production,重复晋升为 no-op
        assert svc.promote_to_production("prom_model") is False
