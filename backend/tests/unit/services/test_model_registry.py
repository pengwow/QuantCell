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


def _make_demo_artifact(td: str, model_id: str, meta_extra: dict | None = None) -> str:
    """造一个训练产物 zip + .meta.json,模拟 rl_service 的落盘方式
    (features 结构对齐 KERNEL_FEATURES;meta_extra 可补 walk_forward 等训练上下文)"""
    meta = {
        "model_id": model_id,
        "spec_version": "v1",
        "window_size": 1,
        "features": [
            {"name": "close", "source": {"PriceField": "close"}, "normalizer": "ZScore", "clip_range": None},
            {"name": "volume", "source": {"VolumeField": "volume"}, "normalizer": "None", "clip_range": None},
        ],
    }
    if meta_extra:
        meta.update(meta_extra)
    zip_path = os.path.join(td, f"{model_id}.zip")
    with open(zip_path, "wb") as f:
        f.write(b"dummy sb3 model")
    with open(zip_path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f)
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
        # 第一个注册的被晋升为 production,其余透传 Rust 最新记录的真实 stage(staging)
        assert list(stages.values()).count("production") == 1
        assert list(stages.values()).count("staging") == 2
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


def test_seed_models_expose_model_card_fields_in_detail():
    from services.model_registry import ModelRegistryService, seed_demo_models

    with tempfile.TemporaryDirectory() as td:
        _make_demo_artifact(td, "rl_model_ppo_1700000000")
        assert seed_demo_models(storage_path=td) == ["rl_model_ppo_1700000000"]

        d = ModelRegistryService(storage_path=td).get_model_detail("rl_model_ppo_1700000000")
        # seed 并入完整 meta 后,detail 可读出特征规格等模型卡字段(并入生效的证明)
        assert d["spec_version"] == "v1"
        assert d["window_size"] == 1
        # metadata 无 algorithm 时从名字 <name>_<algo>_<unixts> 兜底
        assert d["algorithm"] == "ppo"
        assert d["features"] == [
            {"name": "close", "source_display": "PriceField:close", "normalizer": "ZScore", "clip_range": None},
            {"name": "volume", "source_display": "VolumeField:volume", "normalizer": "None", "clip_range": None},
        ]
        assert d["observation_stats_present"] is False
        assert d["walk_forward"] == {}


def test_seed_crops_walk_forward_to_aggregate():
    from services.model_registry import ModelRegistryService, seed_demo_models

    with tempfile.TemporaryDirectory() as td:
        _make_demo_artifact(
            td,
            "rl_model_sac_1700000001",
            meta_extra={
                "walk_forward": {
                    "folds": [{"fold": 0}, {"fold": 1}],
                    "aggregate": {"mean": {"sharpe_ratio": 0.5}, "std": {}, "n_valid_folds": 2},
                }
            },
        )
        seed_demo_models(storage_path=td)

        svc = ModelRegistryService(storage_path=td)
        d = svc.get_model_detail("rl_model_sac_1700000001")
        # folds 明细无消费方,不并入注册表;只保留 OOS 汇总
        assert d["walk_forward"] == {"mean": {"sharpe_ratio": 0.5}, "std": {}, "n_valid_folds": 2}
        assert "folds" not in d["metadata"]


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
        # get_latest 兜底后 stage 为注册后的真实值,version/metrics 不再空占位
        assert row["stage"] == "staging"
        assert row["version"] == "1.0.0"
        assert row["metrics"] == {"sharpe": 1.5}


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


def test_get_model_detail_full_contract():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        model_file = os.path.join(td, "test.onnx")
        with open(model_file, "wb") as f:
            f.write(b"dummy")
        svc.register_model(
            name="detail_model",
            model_path=model_file,
            metadata={"algorithm": "ppo"},
            metrics={"sharpe": 1.5},
        )
        svc.promote_to_production("detail_model")

        detail = svc.get_model_detail("detail_model")
        assert detail is not None
        assert set(detail.keys()) == {
            "name",
            "version",
            "stage",
            "metadata",
            "metrics",
            "artifact_size_bytes",
            "artifact_hash",
            "storage_uri",
            "algorithm",
            "trained_at",
            "spec_version",
            "window_size",
            "features",
            "observation_stats_present",
            "walk_forward",
        }
        assert detail["name"] == "detail_model"
        assert detail["stage"] == "production"
        assert detail["version"] == "1.0.0"
        # description 里除 metadata 外还有 metrics,不得混回 metadata
        assert detail["metadata"] == {"algorithm": "ppo"}
        assert detail["metrics"] == {"sharpe": 1.5}
        assert detail["artifact_size_bytes"] == len(b"dummy")
        assert detail["artifact_hash"]
        assert detail["storage_uri"]
        # 模型卡字段:旧式 metadata 只给 algorithm,其余占位
        assert detail["algorithm"] == "ppo"
        assert detail["spec_version"] == "-"
        assert detail["window_size"] == "-"
        assert detail["features"] == []
        assert detail["observation_stats_present"] is False
        assert detail["walk_forward"] == {}
        # trained_at 兜底为 artifact mtime 的 ISO 毫秒时间戳
        assert detail["trained_at"] != "-" and "T" in detail["trained_at"]


def test_get_model_detail_unpromoted_uses_latest_record():
    """未晋升模型也能出详情:get_latest 兜底,stage 透传真实 staging;
    metadata 聚合出的模型卡字段(特征等)与 production 路径一致。"""
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        model_file = os.path.join(td, "dev.zip")
        with open(model_file, "wb") as f:
            f.write(b"dummy")
        svc.register_model(
            name="devcard_ppo_1700000000",
            model_path=model_file,
            metadata={"features": [{"name": "close", "source": {"PriceField": "close"}}]},
            metrics={"sharpe": 0.8},
        )

        d = svc.get_model_detail("devcard_ppo_1700000000")
        assert d is not None
        assert d["stage"] == "staging"
        assert d["version"] == "1.0.0"
        assert d["metrics"] == {"sharpe": 0.8}
        assert d["features"] == [
            {"name": "close", "source_display": "PriceField:close", "normalizer": None, "clip_range": None}
        ]
        # metadata 无 created_at 时经 get_latest 记录的 storage_uri 做 mtime 兜底
        assert d["trained_at"] != "-" and "T" in d["trained_at"]


def test_get_model_detail_none_for_unknown_model():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        # 未晋升模型由 get_latest 兜底出详情(见 unpromoted 用例);完全不存在的名字才 None
        assert svc.get_model_detail("ghost") is None


def _register_prod(svc, name: str, td: str, metadata: dict | None = None) -> None:
    """注册 + 晋升一个哑模型,供 detail 断言用。"""
    model_file = os.path.join(td, f"{name}.zip")
    with open(model_file, "wb") as f:
        f.write(b"dummy")
    svc.register_model(name=name, model_path=model_file, metadata=metadata)
    assert svc.promote_to_production(name) is True


def test_get_model_detail_model_card_fields():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        _register_prod(
            svc,
            "card_ppo_1700000000",
            td,
            metadata={
                "spec_version": "v1",
                "window_size": 1,
                "algorithm": "ppo",
                "total_timesteps": 10000,
                "created_at": "2026-11-10T15:30:00.000+08:00",
                "features": [
                    {"name": "close", "source": {"PriceField": "close"}, "normalizer": "ZScore", "clip_range": None},
                    {"name": "volume", "source": {"VolumeField": "volume"}, "normalizer": "None", "clip_range": None},
                    # 缺 source 的坏元素必须被跳过,不让整个 detail 500
                    {"name": "broken"},
                ],
                "observation_stats": [{"name": "close", "count": 100}],
                "walk_forward_aggregate": {
                    "mean": {"sharpe_ratio": 1.1},
                    "std": {"sharpe_ratio": 0.2},
                    "n_valid_folds": 3,
                },
            },
        )

        d = svc.get_model_detail("card_ppo_1700000000")
        assert d["algorithm"] == "ppo"
        assert d["trained_at"] == "2026-11-10T15:30:00.000+08:00"
        assert d["spec_version"] == "v1"
        assert d["window_size"] == 1
        # source dict 序列化为 "Key:value" 形式;坏元素被跳过
        assert d["features"] == [
            {"name": "close", "source_display": "PriceField:close", "normalizer": "ZScore", "clip_range": None},
            {"name": "volume", "source_display": "VolumeField:volume", "normalizer": "None", "clip_range": None},
        ]
        assert d["observation_stats_present"] is True
        assert d["walk_forward"] == {"mean": {"sharpe_ratio": 1.1}, "std": {"sharpe_ratio": 0.2}, "n_valid_folds": 3}


def test_get_model_detail_algorithm_fallback_from_name():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        _register_prod(svc, "x_ppo_123", td)
        _register_prod(svc, "plainname", td)
        _register_prod(svc, "rl_model_a", td)

        # 旧数据 metadata 无 algorithm:从 seed 命名 <name>_<algo>_<unixts> 中段兜底
        assert svc.get_model_detail("x_ppo_123")["algorithm"] == "ppo"
        # 尾段不是纯数字(普通命名/短命名)不给错误答案,直接占位
        assert svc.get_model_detail("plainname")["algorithm"] == "-"
        assert svc.get_model_detail("rl_model_a")["algorithm"] == "-"


def test_get_model_detail_corrupted_description_placeholder(monkeypatch):
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        _register_prod(svc, "corrupt", td)
        # 模拟 description 损坏(非 JSON)且 artifact 查不到:必须返回占位而非 500
        # patch 点是 _get_any —— detail 的记录来源已切换为该兜底查询
        monkeypatch.setattr(
            svc,
            "_get_any",
            lambda mid: {
                "name": "corrupt",
                "version": "1.0.0",
                "stage": "production",
                "description": "{not-json",
                "artifact_size_bytes": 5,
                "artifact_hash": "h",
                "storage_uri": "no-such-file.zip",
            },
        )

        d = svc.get_model_detail("corrupt")
        assert d is not None
        assert d["metadata"] == {}
        assert d["algorithm"] == "-"
        assert d["trained_at"] == "-"
        assert d["spec_version"] == "-"
        assert d["window_size"] == "-"
        assert d["features"] == []
        assert d["observation_stats_present"] is False
        assert d["walk_forward"] == {}


def test_get_artifact_path_within_storage():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        model_file = os.path.join(td, "a.onnx")
        with open(model_file, "wb") as f:
            f.write(b"artifact-bytes")
        svc.register_model(name="path_model", model_path=model_file)
        svc.promote_to_production("path_model")

        path = svc.get_artifact_path("path_model")
        assert path is not None
        # Rust fs::copy 后文件在 <storage>/<name>/<version>/ 下,必须仍位于 storage 内
        assert path.startswith(os.path.realpath(td) + os.sep)
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == b"artifact-bytes"


def test_get_artifact_path_rejects_escape(monkeypatch):
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        # 模拟 storage_uri 被改动指向注册表外的文件,必须拒绝
        monkeypatch.setattr(
            svc,
            "get_model",
            lambda mid: {"storage_uri": "/etc/passwd", "name": "evil"},
        )
        assert svc.get_artifact_path("evil") is None
