"""ensemble 测试共享夹具:免真实 SB3 训练,patch 模型目录与加载。"""

import json

import numpy as np
import pytest
from gymnasium import spaces


class FakeSB3Model:
    """predict 按预设输出序列返回;action_space 决定聚合器分支。"""

    def __init__(self, action_space, outputs):
        self.action_space = action_space
        self._outputs = iter(outputs)

    def predict(self, obs, deterministic=True):
        return next(self._outputs), None


DISCRETE_SPACE = spaces.Discrete(3)
BOX_SPACE = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

META_TEMPLATE = {
    "spec_version": "v1",
    "window_size": 3,
    "features": ["f1", "f2", "f3"],
    "observation_stats": {"f1": {"mean": 0.0, "std": 1.0}, "f2": {"mean": 0.0, "std": 1.0}},
}


@pytest.fixture
def ensemble_env(tmp_path, monkeypatch):
    """隔离环境:ENSEMBLES_STORE/MODELS_DIR 指向 tmp,RLService.load_model 返回 FakeSB3Model。

    yield 出 seed(stems, metas, models) -> list[str](model_paths):
    为每个成员写便宜 zip 空文件 + meta 旁车,并注册假模型。
    """
    from services import ensemble_service as es
    from services.rl_service import RLService

    monkeypatch.setattr(es, "ENSEMBLES_STORE", tmp_path / "ensembles.json")
    monkeypatch.setattr(es, "MODELS_DIR", tmp_path / "models")
    es.get_ensemble_service.cache_clear()

    models_dir = tmp_path / "models"
    models_dir.mkdir(exist_ok=True)
    registry: dict[str, FakeSB3Model] = {}

    def fake_load_model(self, path):
        stem = str(path).split("/")[-1].removesuffix(".zip")
        if stem not in registry:
            raise FileNotFoundError(f"未注册的测试成员: {stem}")
        return registry[stem]

    monkeypatch.setattr(RLService, "load_model", fake_load_model, raising=False)

    def seed(stems, metas=None, models=None):
        metas = metas or {s: dict(META_TEMPLATE) for s in stems}
        models = models or {s: FakeSB3Model(DISCRETE_SPACE, [np.int64(1)]) for s in stems}
        paths = []
        for stem in stems:
            (models_dir / f"{stem}.zip").write_bytes(b"fake-zip")
            # meta 旁车命名与 rl_meta_path 口径一致:{zip完整路径}.meta.json
            (models_dir / f"{stem}.zip.meta.json").write_text(json.dumps(metas[stem]), encoding="utf-8")
            registry[stem] = models[stem]
            paths.append(stem)
        return paths

    yield seed
    es.get_ensemble_service.cache_clear()
