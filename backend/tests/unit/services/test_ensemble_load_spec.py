"""load_ensemble_spec 加载 / meta 一致性校验单测(spec §4.3.1)。"""

import numpy as np
import pytest
from gymnasium import spaces

from services.ensemble_aggregator import make_ensemble_predict_fn
from services.ensemble_service import load_ensemble_spec

# 与 services/conftest.py 重复定义,避免跨文件 import
# features 对齐真实落盘形态(rl_service.KERNEL_FEATURES):特征定义 dict 列表
META_TEMPLATE = {
    "spec_version": "v1",
    "window_size": 3,
    "features": [
        {"name": "f1", "source": {"PriceField": "f1"}, "normalizer": "ZScore", "clip_range": None},
        {"name": "f2", "source": {"PriceField": "f2"}, "normalizer": "ZScore", "clip_range": None},
        {"name": "f3", "source": {"PriceField": "f3"}, "normalizer": "ZScore", "clip_range": None},
    ],
    "observation_stats": {"f1": {"mean": 0.0, "std": 1.0}, "f2": {"mean": 0.0, "std": 1.0}},
}
BOX_SPACE = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)
DISCRETE_SPACE = spaces.Discrete(3)


class FakeSB3Model:
    def __init__(self, action_space, outputs):
        self.action_space = action_space
        self._outputs = iter(outputs)

    def predict(self, obs, deterministic=True):
        return next(self._outputs), None


def _seeded_service(ensemble_env, stems, metas=None, models=None):
    paths = ensemble_env(stems, metas=metas, models=models)
    from services import ensemble_service

    svc = ensemble_service.get_ensemble_service()
    ensemble_id, skipped = svc.create_ensemble(strategy="soft_vote", model_paths=paths)
    return ensemble_id, skipped


def test_load_spec_returns_member_fns_and_base_meta(ensemble_env):
    eid, skipped = _seeded_service(
        ensemble_env,
        ["m1", "m2"],
        models={
            "m1": FakeSB3Model(BOX_SPACE, [np.array([0.8], dtype=np.float32)]),
            "m2": FakeSB3Model(DISCRETE_SPACE, [np.int64(1)]),
        },
    )
    assert skipped == []

    spec = load_ensemble_spec(eid)
    assert spec.model_id == eid
    assert spec.meta["spec_version"] == "v1"
    assert spec.meta["window_size"] == 3
    # 内核形态冒烟:一份特征向量 → 聚合 ratio(连续 0.8 与离散 buy→1.0 的均值)
    fn = make_ensemble_predict_fn(spec.member_predict_fns)
    assert fn([0.0, 0.0, 0.0]) == pytest.approx(0.9)


def test_load_spec_rejects_missing_ensemble():
    with pytest.raises(ValueError, match="nope"):
        load_ensemble_spec("nope")


def test_load_spec_rejects_meta_mismatch(ensemble_env):
    paths = ensemble_env(["m1", "m2"], metas={"m1": dict(META_TEMPLATE), "m2": {**META_TEMPLATE, "window_size": 10}})
    from services import ensemble_service

    svc = ensemble_service.get_ensemble_service()
    # 绕过 create 同款校验:模拟 records 落盘后成员 meta 文件发生漂移(window_size 改变)
    eid = "ens_drift"
    svc._records[eid] = {
        "id": eid,
        "strategy": "soft_vote",
        "model_paths": list(paths),
        "members": [],
        "created_at": 0,
    }
    with pytest.raises(ValueError, match="window_size"):
        load_ensemble_spec(eid)


def test_create_rejects_member_without_meta(ensemble_env):
    """成员 zip 存在但缺 meta.json → 创建期整体拒绝(spec §4.2)。"""
    from services import ensemble_service

    es = ensemble_service.get_ensemble_service()
    (ensemble_service.MODELS_DIR / "bad.zip").write_bytes(b"fake")
    with pytest.raises(ValueError, match="meta"):
        es.create_ensemble(strategy="soft_vote", model_paths=["bad"])


def test_load_spec_requires_spec_version_match(ensemble_env):
    eid, _ = _seeded_service(ensemble_env, ["m1"])
    with pytest.raises(ValueError, match="spec_version"):
        load_ensemble_spec(eid, spec_version="v999")
