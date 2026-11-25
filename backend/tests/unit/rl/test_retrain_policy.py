"""services.retrain_policy 单元测试：触发 / 冷却 / 日上限 / 幂等。

全部用临时 models 目录 + 合成旁车，不碰真实训练、不读真实 data/models。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import services.retrain_policy as policy_mod
from services.retrain_policy import (
    REASON_OOS_DECAY,
    REASON_STALE,
    RetrainPolicy,
    family_snapshots,
    record_retrain,
    retrained_today,
    select_retrain_candidates,
)

NOW = datetime(2026, 11, 18, 3, 40, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate_history(tmp_path, monkeypatch):
    """历史/状态落在临时目录：QUANTCELL_RL_LIFECYCLE_DIR 优先级最高，必须清掉。"""
    monkeypatch.delenv("QUANTCELL_RL_LIFECYCLE_DIR", raising=False)
    for env in (
        "QUANTCELL_RETRAIN_MAX_PER_DAY",
        "QUANTCELL_RETRAIN_COOLDOWN_DAYS",
        "QUANTCELL_RETRAIN_STALE_DAYS",
        "QUANTCELL_RETRAIN_OOS_DECAY_RATIO",
    ):
        monkeypatch.delenv(env, raising=False)


def _write_model(
    models_dir: Path,
    model_id: str,
    *,
    created_at: datetime,
    train_sharpe: float | None = None,
    oos_sharpe: float | None = None,
    with_zip: bool = True,
) -> None:
    if with_zip:
        (models_dir / f"{model_id}.zip").write_bytes(b"")
    meta: dict = {"model_id": model_id, "created_at": created_at.isoformat()}
    if train_sharpe is not None or oos_sharpe is not None:
        meta["walk_forward"] = {
            "aggregate": {"mean": {"sharpe_ratio": train_sharpe, "total_return_pct": 12.0}},
            "oos": {"sharpe_ratio": oos_sharpe, "total_return_pct": 4.0},
        }
    (models_dir / f"{model_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_oos_decay_triggers_retrain(tmp_path):
    _write_model(
        tmp_path,
        "BTCUSDT_v1_ppo_1700000000",
        created_at=NOW - timedelta(days=1),
        train_sharpe=2.0,
        oos_sharpe=0.4,
    )

    candidates = select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy())

    assert [c.family for c in candidates] == ["BTCUSDT"]
    assert candidates[0].reason == REASON_OOS_DECAY
    assert candidates[0].model_path == str(tmp_path / "BTCUSDT_v1_ppo_1700000000.zip")
    assert candidates[0].evidence["oos_sharpe"] == pytest.approx(0.4)


def test_healthy_family_is_not_selected(tmp_path):
    _write_model(
        tmp_path,
        "ETHUSDT_v1_ppo_1700000000",
        created_at=NOW - timedelta(days=1),
        train_sharpe=2.0,
        oos_sharpe=1.8,
    )

    assert select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy()) == []


def test_stale_data_triggers_retrain(tmp_path):
    _write_model(tmp_path, "SOLUSDT_v1_ppo_1700000000", created_at=NOW - timedelta(days=20))

    candidates = select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy(stale_days=14.0))

    assert [c.reason for c in candidates] == [REASON_STALE]
    assert candidates[0].evidence["age_days"] == pytest.approx(20.0, abs=0.1)


def test_cooldown_skips_recently_retrained_family(tmp_path):
    _write_model(
        tmp_path,
        "BTCUSDT_v1_ppo_1700000000",
        created_at=NOW - timedelta(days=1),
        train_sharpe=2.0,
        oos_sharpe=0.4,
    )
    record_retrain("BTCUSDT", model_id="BTCUSDT_retrain_x", at=NOW - timedelta(days=1), models_dir=tmp_path)

    assert select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy(cooldown_days=3)) == []


def test_daily_cap_limits_families(tmp_path):
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        _write_model(
            tmp_path,
            f"{symbol}_v1_ppo_1700000000",
            created_at=NOW - timedelta(days=2),
            train_sharpe=2.0,
            oos_sharpe=0.1,
        )

    candidates = select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy(max_per_day=2))

    assert len(candidates) == 2


def test_same_day_retrain_is_idempotent(tmp_path):
    _write_model(
        tmp_path,
        "BTCUSDT_v1_ppo_1700000000",
        created_at=NOW - timedelta(days=1),
        train_sharpe=2.0,
        oos_sharpe=0.4,
    )
    record_retrain("BTCUSDT", model_id="BTCUSDT_retrain_y", at=NOW, models_dir=tmp_path)

    history = policy_mod.load_retrain_history(tmp_path)
    assert retrained_today(history, "BTCUSDT", NOW.date()) is True
    assert select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy()) == []


def test_missing_zip_is_skipped(tmp_path):
    _write_model(
        tmp_path,
        "BTCUSDT_v1_ppo_1700000000",
        created_at=NOW - timedelta(days=20),
        with_zip=False,
    )

    assert family_snapshots(tmp_path, now=NOW)["BTCUSDT"]["model_path"] is None
    assert select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy()) == []


def test_old_meta_without_walk_forward_never_decays(tmp_path):
    """旧产物只有 aggregate/无 OOS：不可判衰减，只能靠数据新鲜度触发。"""
    _write_model(tmp_path, "ADAUSDT_v1_ppo_1700000000", created_at=NOW - timedelta(days=2))

    snapshot = family_snapshots(tmp_path, now=NOW)["ADAUSDT"]
    assert snapshot["oos_sharpe"] is None
    assert select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy()) == []


# ==================== 参数解析 ====================


def test_policy_from_env_overrides(monkeypatch):
    monkeypatch.setenv("QUANTCELL_RETRAIN_MAX_PER_DAY", "5")
    monkeypatch.setenv("QUANTCELL_RETRAIN_COOLDOWN_DAYS", "7.5")
    monkeypatch.setenv("QUANTCELL_RETRAIN_STALE_DAYS", "30")
    monkeypatch.setenv("QUANTCELL_RETRAIN_OOS_DECAY_RATIO", "0.8")

    policy = RetrainPolicy.from_env()

    assert (policy.max_per_day, policy.cooldown_days, policy.stale_days, policy.oos_decay_ratio) == (
        5,
        7.5,
        30.0,
        0.8,
    )


def test_policy_from_env_ignores_garbage(monkeypatch):
    monkeypatch.setenv("QUANTCELL_RETRAIN_MAX_PER_DAY", "not-a-number")
    monkeypatch.setenv("QUANTCELL_RETRAIN_COOLDOWN_DAYS", "")

    policy = RetrainPolicy.from_env()

    assert policy.max_per_day == policy_mod.MAX_RETRAINS_PER_DAY
    assert policy.cooldown_days == policy_mod.COOLDOWN_DAYS


def test_history_survives_corrupted_file(tmp_path):
    target = policy_mod.history_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not json", encoding="utf-8")

    assert policy_mod.load_retrain_history(tmp_path) == []


def test_family_snapshots_accepts_rl_service_sidecar_naming(tmp_path):
    """回归：rl_service 落盘的旁车是 `<stem>.zip.meta.json`——必须能配对 zip。

    此前 zip_path 按 `<stem>.zip` 拼接（stem 已含 .zip），真实目录上恒缺失，
    自动重训永远选不出候选；仅 synthetic `X.meta.json` 命名的单测掩盖了该错位。
    """
    model_id = "BTCUSDT_ppo_1794974672"
    (tmp_path / f"{model_id}.zip").write_bytes(b"")
    (tmp_path / f"{model_id}.zip.meta.json").write_text(
        json.dumps({"model_id": model_id, "created_at": (NOW - timedelta(days=20)).isoformat()}),
        encoding="utf-8",
    )
    snaps = family_snapshots(tmp_path, now=NOW)
    assert snaps["BTCUSDT"]["model_id"] == model_id
    assert snaps["BTCUSDT"]["model_path"] == str(tmp_path / f"{model_id}.zip")
    cands = select_retrain_candidates(tmp_path, now=NOW, policy=RetrainPolicy(stale_days=14.0))
    assert [(c.family, c.reason) for c in cands] == [("BTCUSDT", REASON_STALE)]
