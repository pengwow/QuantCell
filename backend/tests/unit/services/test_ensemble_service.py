"""EnsembleService 单元测试:方案 A 语义下的创建/持久化/删除守护。

旧的 Rust 投票 / pickle / SB3 直加载测试随 ensemble_service 重构移除
(由 test_ensemble_load_spec.py 承接加载口径),本文件只覆盖 EnsembleService
公共 API 的 records 行为。模型细节由 conftest.ensemble_env 的 FakeSB3Model 替代。
"""


def test_ensemble_service_creation(ensemble_env):
    from services.ensemble_service import EnsembleService

    svc = EnsembleService()
    assert svc is not None


def test_create_records_members(ensemble_env):
    paths = ensemble_env(["m1"])
    from services import ensemble_service

    svc = ensemble_service.get_ensemble_service()
    eid, skipped = svc.create_ensemble("soft_vote", paths)
    assert skipped == []
    rec = svc.list_ensembles()[0]
    assert rec["id"] == eid
    assert rec["members"][0]["stem"] == "m1"
    assert rec["members"][0]["action_space"] == "discrete"


def test_persistence_and_restart(ensemble_env, tmp_path):
    paths = ensemble_env(["m1"])
    from services import ensemble_service

    svc = ensemble_service.get_ensemble_service()
    eid, _ = svc.create_ensemble("soft_vote", paths)
    assert (tmp_path / "ensembles.json").exists()

    # 模拟重启:新实例从磁盘恢复元数据
    svc2 = ensemble_service.EnsembleService()
    items = svc2.list_ensembles()
    assert len(items) == 1
    assert items[0]["id"] == eid
    assert items[0]["created_at"] is not None


def test_delete_ensemble(ensemble_env):
    paths = ensemble_env(["m1"])
    from services.ensemble_service import EnsembleService

    svc = EnsembleService()
    eid, _ = svc.create_ensemble("soft_vote", paths)

    svc.delete_ensemble(eid)
    assert svc.list_ensembles() == []
    # 删除后文件同步重写,重启不会复活
    assert not EnsembleService().list_ensembles()
    # 删除不存在的 id → KeyError
    import pytest as _pytest

    with _pytest.raises(KeyError):
        svc.delete_ensemble(eid)


def test_predict_zero_observation_fills_features(ensemble_env):
    """D1 零观测冒烟:空 observation → 按 meta.features 全填 0.0,前端无需感知特征列表。

    FakeSB3Model 离散动作 1 → ratio 1.0,两成员均值 1.0、置信度 clip(1-0)=1.0。
    """
    paths = ensemble_env(["m1", "m2"])
    from services.ensemble_service import get_ensemble_service

    svc = get_ensemble_service()
    eid, _ = svc.create_ensemble("mean", paths)

    result = svc.predict(eid, {})
    assert result["action_type"] == "buy"
    assert result["ratio"] == 1.0
    assert result["confidence"] == 1.0
    assert result["members"] == [
        {"stem": "m1", "ratio": 1.0},
        {"stem": "m2", "ratio": 1.0},
    ]


def test_predict_nonempty_observation_missing_features_still_rejected(ensemble_env):
    """D1 只放宽空 dict;非空观测缺特征仍 ValueError(路由层转 400)。"""
    import pytest

    paths = ensemble_env(["m1"])
    from services.ensemble_service import EnsembleService

    svc = EnsembleService()
    eid, _ = svc.create_ensemble("mean", paths)
    # meta 有 f1/f2/f3,只给 f1 → 缺特征报错
    with pytest.raises(ValueError, match="缺少特征"):
        svc.predict(eid, {"f1": 0.0})
