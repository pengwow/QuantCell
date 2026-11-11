"""_load_rl_spec 集成分支测试:只验接线与 spec 组装,加载逻辑由 services 层单测覆盖。"""

import numpy as np
import pytest
from gymnasium import spaces

from services.ensemble_aggregator import member_ratio_predict_fn
from services.ensemble_service import PredictMemberSpecs
from services.rl_service import KERNEL_ACTION_SPACE, KERNEL_SPEC_VERSION
from worker.strategy_manager import worker_system

META = {
    "spec_version": KERNEL_SPEC_VERSION,
    "window_size": 3,
    "features": ["f1", "f2", "f3"],
}


def _fake_member_specs():
    class _FakeBoxModel:
        action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        def predict(self, obs, deterministic=True):
            return np.array([0.6], dtype=np.float32), None

    return PredictMemberSpecs(
        member_predict_fns=[member_ratio_predict_fn(_FakeBoxModel())],
        meta=dict(META),
        model_id="ens_test",
        representative_path="/tmp/fake.zip",
    )


def test_load_rl_spec_ensemble_branch_assembles_kernel_spec(monkeypatch):
    import services.ensemble_service as es

    monkeypatch.setattr(es, "load_ensemble_spec", lambda eid, **kw: _fake_member_specs())

    spec = worker_system._load_rl_spec(1, {"ensemble_id": "ens_test"})
    assert spec["model_id"] == "ens_test"
    assert spec["spec_version"] == KERNEL_SPEC_VERSION
    assert spec["window_size"] == 3
    assert spec["features"] == ["f1", "f2", "f3"]
    assert spec["action_space"] == KERNEL_ACTION_SPACE
    # 本测试 META 不带 observation_stats → stats 为 None(deterministic 行为)
    assert spec["stats"] is None
    # predict 是聚合器产物:obs → ratio
    assert spec["predict"]([0.0, 0.0, 0.0]) == pytest.approx(0.6)


def test_load_rl_spec_ensemble_id_takes_priority(monkeypatch):
    import services.ensemble_service as es

    monkeypatch.setattr(es, "load_ensemble_spec", lambda eid, **kw: _fake_member_specs())
    spec = worker_system._load_rl_spec(1, {"ensemble_id": "ens_test", "model_path": "/tmp/x.zip"})
    assert spec["model_id"] == "ens_test"  # 走集成分支,未触碰 model_path


def test_load_rl_spec_ensemble_load_failure_propagates(monkeypatch):
    import services.ensemble_service as es

    def boom(eid, **kw):
        raise ValueError(f"集成 {eid} 不存在")

    monkeypatch.setattr(es, "load_ensemble_spec", boom)
    with pytest.raises(ValueError, match="不存在"):
        worker_system._load_rl_spec(1, {"ensemble_id": "ens_missing"})


def test_load_rl_spec_missing_both_params():
    # 无 ensemble_id 且无 model_path 时,行为与旧版一致(缺少 model_path 参数)
    with pytest.raises(ValueError, match="缺少 model_path"):
        worker_system._load_rl_spec(1, {})
