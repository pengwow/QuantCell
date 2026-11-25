"""services.oos_gate 单元测试:model family 归约 + 连续 N 轮 OOS 拦停。"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from services.oos_gate import (
    OosGateError,
    audit_oos_gate,
    check_oos_gate,
    model_family,
    round_passes,
)


def _write_meta(td: str, model_id: str, *, sharpe: float | None, ret: float | None, created_at: str) -> None:
    meta = {
        "model_id": model_id,
        "created_at": created_at,
        "walk_forward": {"oos": {"sharpe_ratio": sharpe, "total_return_pct": ret}},
    }
    with open(os.path.join(td, f"{model_id}.meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)


def _register(svc, td: str, name: str) -> None:
    artifact = os.path.join(td, f"{name}.zip")
    with open(artifact, "wb") as f:
        f.write(b"fake-sb3-bytes")
    svc.register_model(name=name, model_path=artifact, metadata={"algorithm": "ppo"})


def test_model_family_normalizes_training_rounds():
    assert model_family("BTCUSDT_v1_ppo_1700000000") == "BTCUSDT"
    assert model_family("BTCUSDT_retrain_1700000000_ppo_1700000001") == "BTCUSDT"
    assert model_family("gate_model_ppo_1700000000") == "gate_model"
    assert model_family("plain_name") == "plain_name"


def test_round_passes_uses_loose_defaults():
    assert round_passes(0.1, 0.5) is True
    assert round_passes(0.0, 0.0) is True
    assert round_passes(-0.1, 1.0) is False
    assert round_passes(0.5, -0.1) is False
    assert round_passes(None, 1.0) is None


def test_blocked_when_latest_two_rounds_both_fail():
    with tempfile.TemporaryDirectory() as td:
        _write_meta(td, "gate_model_ppo_1700000000", sharpe=-0.2, ret=-1.5, created_at="2026-01-01T00:00:00.000")
        _write_meta(td, "gate_model_ppo_1700000001", sharpe=-0.1, ret=-0.5, created_at="2026-01-02T00:00:00.000")

        result = check_oos_gate("gate_model", td)

        assert result["blocked"] is True
        assert result["rounds_checked"] == 2
        assert len(result["failed_rounds"]) == 2
        assert "连续 2 轮" in result["reason"]


def test_not_blocked_when_one_of_latest_two_passes():
    with tempfile.TemporaryDirectory() as td:
        _write_meta(td, "gate_model_ppo_1700000000", sharpe=1.2, ret=2.0, created_at="2026-01-01T00:00:00.000")
        _write_meta(td, "gate_model_ppo_1700000001", sharpe=-0.1, ret=-0.5, created_at="2026-01-02T00:00:00.000")

        result = check_oos_gate("gate_model", td)

        assert result["blocked"] is False
        assert "未构成连续失败" in result["reason"]


def test_not_blocked_with_fewer_than_required_rounds():
    with tempfile.TemporaryDirectory() as td:
        _write_meta(td, "gate_model_ppo_1700000000", sharpe=-0.2, ret=-1.5, created_at="2026-01-01T00:00:00.000")

        result = check_oos_gate("gate_model", td)

        assert result["blocked"] is False
        assert "轮次不足" in result["reason"]


def test_legacy_aggregate_mean_is_used_when_no_oos_key():
    with tempfile.TemporaryDirectory() as td:
        for i in range(2):
            meta = {
                "model_id": f"legacy_model_ppo_170000000{i}",
                "created_at": f"2026-01-0{i + 1}T00:00:00.000",
                "walk_forward": {"aggregate": {"mean": {"sharpe_ratio": -0.3, "total_return_pct": -2.0}}},
            }
            with open(os.path.join(td, f"legacy_model_ppo_170000000{i}.meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)

        result = check_oos_gate("legacy_model", td)

        assert result["blocked"] is True
        assert result["rounds"][0]["source"] == "walk_forward.aggregate.mean"


def test_promote_raises_with_evidence():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        _register(svc, td, "gate_model")
        _write_meta(td, "gate_model_ppo_1700000000", sharpe=-0.2, ret=-1.5, created_at="2026-01-01T00:00:00.000")
        _write_meta(td, "gate_model_ppo_1700000001", sharpe=-0.1, ret=-0.5, created_at="2026-01-02T00:00:00.000")

        with pytest.raises(OosGateError) as exc:
            svc.promote_to_production("gate_model")

        message = str(exc.value)
        assert "连续 2 轮" in message
        assert "sharpe=-0.2" in message
        assert "return%=-1.5" in message
        # 拦停后不得落到 production
        assert svc.get_model("gate_model") is None


def test_promote_bypass_succeeds_for_bootstrap():
    from services.model_registry import ModelRegistryService

    with tempfile.TemporaryDirectory() as td:
        svc = ModelRegistryService(storage_path=td)
        _register(svc, td, "gate_model")
        _write_meta(td, "gate_model_ppo_1700000000", sharpe=-0.2, ret=-1.5, created_at="2026-01-01T00:00:00.000")
        _write_meta(td, "gate_model_ppo_1700000001", sharpe=-0.1, ret=-0.5, created_at="2026-01-02T00:00:00.000")

        assert svc.promote_to_production("gate_model", enforce_oos_gate=False) is True
        assert svc.get_model("gate_model")["stage"] == "production"


def test_audit_reports_all_families():
    with tempfile.TemporaryDirectory() as td:
        _write_meta(td, "family_a_ppo_1700000000", sharpe=-0.2, ret=-1.0, created_at="2026-01-01T00:00:00.000")
        _write_meta(td, "family_a_ppo_1700000001", sharpe=-0.1, ret=-1.0, created_at="2026-01-02T00:00:00.000")
        _write_meta(td, "family_b_ppo_1700000000", sharpe=1.0, ret=3.0, created_at="2026-01-01T00:00:00.000")

        results = {r["family"]: r for r in audit_oos_gate(td)}

        assert results["family_a"]["blocked"] is True
        assert results["family_b"]["blocked"] is False
