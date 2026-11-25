"""rl.lifecycle 自动闭环（P4-3）单元测试。

覆盖：shadow 对照降级路径 / promote 双闸默认态 / OOS 闸门 / 单族异常隔离 /
同日幂等 / 调度 job 异常隔离。训练与回测全部 monkeypatch，不跑真实训练。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import rl.lifecycle as lifecycle_mod
from rl.lifecycle import (
    AutoCycleConfig,
    _shadow_win_streak,
    load_lifecycle_state,
    pending_promotions,
    run_auto_retrain_cycle,
    shadow_compare,
)
from services.retrain_policy import RetrainPolicy, load_retrain_history

NOW = datetime(2026, 11, 18, 3, 40, tzinfo=UTC)


# ==================== 夹具 ====================


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for env in ("QUANTCELL_RL_LIFECYCLE_DIR", "QUANTCELL_AUTO_RETRAIN", "QUANTCELL_AUTO_PROMOTE"):
        monkeypatch.delenv(env, raising=False)


def _seed_champion(
    models_dir: Path,
    model_id: str,
    *,
    created_at: datetime,
    train_sharpe: float = 3.0,
    oos_sharpe: float = 1.0,
    oos_return_pct: float = 4.0,
) -> None:
    (models_dir / f"{model_id}.zip").write_bytes(b"")
    meta = {
        "model_id": model_id,
        "created_at": created_at.isoformat(),
        "algorithm": "ppo",
        "reward_type": "pnl",
        "data_type": "kline",
        "obs_mode": "features",
        "obs_window": 1,
        "transaction_cost": 0.0004,
        "walk_forward": {
            "aggregate": {"mean": {"sharpe_ratio": train_sharpe, "total_return_pct": 12.0}},
            "oos": {"sharpe_ratio": oos_sharpe, "total_return_pct": oos_return_pct},
        },
    }
    (models_dir / f"{model_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


class FakeTrainer:
    """替换 submit_train_task / get_task：立即返回 done 或 error。"""

    def __init__(self, models_dir: Path, *, fail_families: frozenset[str] = frozenset()):
        self.models_dir = models_dir
        self.fail_families = fail_families
        self.calls: list = []
        self._tasks: dict[str, object] = {}

    def submit(self, config):
        task_id = f"t{len(self.calls)}"
        self.calls.append(config)
        self._tasks[task_id] = config
        return task_id

    def get(self, task_id):
        config = self._tasks[task_id]
        if config.symbol in self.fail_families:
            return SimpleNamespace(snapshot=lambda: {"status": "error", "error": "boom"})
        path = self.models_dir / f"{config.model_name}.zip"
        path.write_bytes(b"")
        return SimpleNamespace(snapshot=lambda: {"status": "done", "model_path": str(path)})


class FakeSvc:
    """RLService 替身：按模型 stem 返回预置回测指标。"""

    def __init__(self, bt_by_stem: dict[str, dict] | None = None, *, raises: bool = False):
        self.bt_by_stem = bt_by_stem or {}
        self.raises = raises
        self.bt_calls: list[tuple[str, str]] = []

    def run_backtest(self, model_path: str, symbol: str, interval: str = "1h", **kwargs):
        stem = Path(model_path).stem
        self.bt_calls.append((stem, symbol))
        if self.raises:
            raise ValueError("回测数据缺失")
        if stem in self.bt_by_stem:
            return self.bt_by_stem[stem]
        # 缺省口径：重训产物（retrain）小幅胜出，champion 弱一些
        if "retrain" in stem:
            return {"sharpe_ratio": 1.6, "total_pnl": 400.0, "max_drawdown_pct": -2.0, "num_trades": 40}
        return {"sharpe_ratio": 0.8, "total_pnl": 100.0, "max_drawdown_pct": -3.0, "num_trades": 30}


def _install(monkeypatch, models_dir: Path, *, trainer=None, svc=None):
    trainer = trainer or FakeTrainer(models_dir)
    svc = svc or FakeSvc()
    monkeypatch.setattr(lifecycle_mod, "submit_train_task", trainer.submit)
    monkeypatch.setattr(lifecycle_mod, "get_task", trainer.get)
    monkeypatch.setattr(lifecycle_mod, "RLService", lambda: svc)
    registered: list[str] = []
    promoted: list[str] = []
    monkeypatch.setattr(
        lifecycle_mod,
        "register_staging",
        lambda path, metadata: registered.append(Path(path).stem) or {"registered": True, "version": "1.0.0"},
    )
    monkeypatch.setattr(
        lifecycle_mod,
        "promote_challenger",
        lambda model_id, **kwargs: promoted.append(model_id) or {"promoted": True},
    )
    return trainer, svc, registered, promoted


def _config(models_dir: Path, **overrides) -> AutoCycleConfig:
    base = {
        "retrain_timesteps": 16,
        "interval": "1h",
        "policy": RetrainPolicy(max_per_day=2, cooldown_days=3.0, stale_days=14.0, oos_decay_ratio=0.5),
        "models_dir": models_dir,
    }
    base.update(overrides)
    return AutoCycleConfig(**base)


def _decayed_champion(models_dir: Path, symbol: str = "BTCUSDT") -> str:
    model_id = f"{symbol}_v1_ppo_1700000000"
    _seed_champion(models_dir, model_id, created_at=NOW - timedelta(days=2), train_sharpe=3.0, oos_sharpe=1.0)
    return model_id


# ==================== shadow 对照（降级路径） ====================


def test_shadow_compare_marks_degraded_and_picks_challenger():
    svc = FakeSvc(
        {
            "champion": {"sharpe_ratio": 0.8, "total_pnl": 100.0},
            "challenger": {"sharpe_ratio": 1.6, "total_pnl": 400.0},
        }
    )

    report = shadow_compare(
        "champion.zip",
        "challenger.zip",
        symbol="BTCUSDT",
        interval="1h",
        reward_type="pnl",
        svc=svc,
    )

    assert report["winner"] == "challenger"
    assert report["degraded"] is True
    assert report["engine"] == "trading_env"
    assert "shadow" in report["degraded_reason"]
    assert report["champion"]["sharpe_ratio"] == 0.8
    # 两条回测用同一 symbol/interval（同窗口口径）
    assert [call[1] for call in svc.bt_calls] == ["BTCUSDT", "BTCUSDT"]


def test_shadow_compare_backtest_failure_is_inconclusive():
    report = shadow_compare(
        "champion.zip",
        "challenger.zip",
        symbol="BTCUSDT",
        interval="1h",
        reward_type="pnl",
        svc=FakeSvc(raises=True),
    )

    assert report["winner"] is None
    assert "回测失败" in report["error"]


def test_shadow_win_streak_counts_consecutive_days_taking_last_entry():
    entries = [
        {"date": "2026-11-14", "winner": "challenger"},
        {"date": "2026-11-15", "winner": "champion"},
        {"date": "2026-11-16", "winner": "challenger"},
        {"date": "2026-11-16", "winner": "challenger"},
        {"date": "2026-11-17", "winner": "challenger"},
    ]

    assert _shadow_win_streak(entries) == 2


# ==================== 闭环主流程 ====================


def test_cycle_leaves_challenger_pending_review_by_default(tmp_path, monkeypatch):
    """AUTO_PROMOTE 缺省 → 只写晋升待审（challenger 停留 staging），不自动 promote。"""
    champion_id = _decayed_champion(tmp_path)
    trainer, _svc, registered, promoted = _install(monkeypatch, tmp_path)

    summary = run_auto_retrain_cycle(_config(tmp_path), now=NOW)

    assert summary["auto_promote"] is False
    assert [c["family"] for c in summary["candidates"]] == ["BTCUSDT"]
    assert summary["results"][0]["status"] == "pending_review"
    assert promoted == []  # 双闸：第二道闸关闭
    assert len(registered) == 1  # 但 challenger 已注册 staging 待审
    assert len(trainer.calls) == 1

    records = pending_promotions(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "pending"
    assert record["champion_id"] == champion_id
    evidence = record["evidence"]
    assert evidence["champion"]["model_id"] == champion_id
    assert evidence["challenger"]["sharpe_ratio"] == 1.6
    assert evidence["shadow"]["streak_days"] == 1
    assert evidence["oos_gate"]["blocked"] is False
    # 重训历史已落盘（同日幂等的依据）
    assert load_retrain_history(tmp_path)[0]["family"] == "BTCUSDT"


def test_cycle_auto_promotes_only_with_second_gate(tmp_path, monkeypatch):
    _decayed_champion(tmp_path)
    monkeypatch.setenv("QUANTCELL_AUTO_PROMOTE", "1")
    _trainer, _svc, _registered, promoted = _install(monkeypatch, tmp_path)

    summary = run_auto_retrain_cycle(_config(tmp_path), now=NOW)

    assert summary["auto_promote"] is True
    assert summary["results"][0]["status"] == "auto_promoted"
    assert len(promoted) == 1
    # 已自动晋升的不再是「待审」，但全量记录里可追溯
    assert pending_promotions(tmp_path) == []
    assert load_lifecycle_state(tmp_path)["promotions"][0]["status"] == "auto_promoted"


def test_cycle_waits_for_required_shadow_win_days(tmp_path, monkeypatch):
    _decayed_champion(tmp_path)
    _install(monkeypatch, tmp_path)

    summary = run_auto_retrain_cycle(_config(tmp_path, required_shadow_win_days=3), now=NOW)

    assert summary["results"][0]["status"] == "shadow_running"
    assert summary["results"][0]["shadow"]["streak_days"] == 1
    assert pending_promotions(tmp_path) == []


def test_cycle_blocks_promotion_when_oos_gate_fails(tmp_path, monkeypatch):
    # 同族两轮 OOS 均为负 → check_oos_gate 判 blocked
    _seed_champion(
        tmp_path,
        "BTCUSDT_v1_ppo_1700000000",
        created_at=NOW - timedelta(days=3),
        train_sharpe=3.0,
        oos_sharpe=-1.0,
        oos_return_pct=-5.0,
    )
    _seed_champion(
        tmp_path,
        "BTCUSDT_v1_ppo_1700000001",
        created_at=NOW - timedelta(days=1),
        train_sharpe=3.0,
        oos_sharpe=-1.5,
        oos_return_pct=-6.0,
    )
    _install(monkeypatch, tmp_path)

    summary = run_auto_retrain_cycle(_config(tmp_path), now=NOW)

    assert summary["results"][0]["status"] == "oos_blocked"
    assert summary["results"][0]["oos"]["blocked"] is True
    assert pending_promotions(tmp_path) == []


def test_cycle_isolates_single_family_failure(tmp_path, monkeypatch):
    _decayed_champion(tmp_path, "BTCUSDT")
    _decayed_champion(tmp_path, "ETHUSDT")
    trainer = FakeTrainer(tmp_path, fail_families=frozenset({"ETHUSDT"}))
    _install(monkeypatch, tmp_path, trainer=trainer)

    summary = run_auto_retrain_cycle(_config(tmp_path), now=NOW)

    statuses = {r["family"]: r["status"] for r in summary["results"]}
    assert statuses == {"BTCUSDT": "pending_review", "ETHUSDT": "error"}
    assert "boom" in next(r["error"] for r in summary["results"] if r["family"] == "ETHUSDT")
    # 失败族也记历史：冷却期内不会再被反复重训
    assert {r["family"] for r in load_retrain_history(tmp_path)} == {"BTCUSDT", "ETHUSDT"}


def test_cycle_is_idempotent_within_same_day(tmp_path, monkeypatch):
    _decayed_champion(tmp_path)
    _install(monkeypatch, tmp_path)

    first = run_auto_retrain_cycle(_config(tmp_path), now=NOW)
    second = run_auto_retrain_cycle(_config(tmp_path), now=NOW)

    assert len(first["candidates"]) == 1
    assert second["candidates"] == []
    assert second["results"] == []


# ==================== 调度 job 异常隔离 ====================


def test_scheduler_job_swallows_exceptions(monkeypatch):
    import core.scheduler as scheduler_mod

    monkeypatch.setattr(
        "rl.lifecycle.run_auto_retrain_cycle",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("调度失败")),
    )

    assert scheduler_mod.run_auto_retrain_job() is None


def test_scheduler_registers_job_only_when_gate_on(monkeypatch):
    import core.scheduler as scheduler_mod

    monkeypatch.delenv("QUANTCELL_AUTO_RETRAIN", raising=False)
    off = scheduler_mod.start_scheduler()
    try:
        assert "rl_auto_retrain" not in {job.id for job in off.get_jobs()}
    finally:
        off.shutdown(wait=False)

    monkeypatch.setenv("QUANTCELL_AUTO_RETRAIN", "1")
    on = scheduler_mod.start_scheduler()
    try:
        assert "rl_auto_retrain" in {job.id for job in on.get_jobs()}
    finally:
        on.shutdown(wait=False)
