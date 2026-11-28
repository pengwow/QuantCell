"""worker.resume_auto_recovery 单元测试。

自动恢复 = resume 守卫拒绝后自动归档 journal 并以交易所为准 fresh start。
本测试文件只覆盖决策层（前缀/ndjson/开关止损/撤单/编排）；驱动线程挂钩的
行为验证见 Task 6 与 docs/testing/pages/strategy-worker.md 手工用例。
"""

import json
import time
from pathlib import Path

import pytest

from worker import resume_auto_recovery as rar


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "celldata"
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(d))
    return d


# ---------- 前缀判定 ----------


def test_is_resume_guard_reject_matches_rust_prefix():
    value = "恢复守卫拒绝继续交易，请人工核对持仓与资金后重试 resume: 持仓断裂（对账报告已落盘: x）"
    assert rar.is_resume_guard_reject(value)


def test_is_resume_guard_reject_rejects_other_errors():
    assert not rar.is_resume_guard_reject("journal 重演失败: bad entry")
    assert not rar.is_resume_guard_reject("")
    # 前缀必须出现在开头，中间匹配不算
    assert not rar.is_resume_guard_reject("error: 恢复守卫拒绝继续交易")


# ---------- ndjson 记录与计数 ----------


def test_recovery_log_path_honors_data_dir(data_dir):
    p = rar.recovery_log_path(901)
    assert p == data_dir / "live" / "worker_901.auto_recovery.ndjson"


def test_record_recovery_appends_one_json_row(data_dir):
    rar.record_recovery(901, {"position_breaks": 1})
    path = rar.recovery_log_path(901)
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["worker_id"] == 901
    assert row["verdict"] == "adopted"
    assert row["reconcile_report"] == {"position_breaks": 1}
    # RFC 3339：含时区偏移的可解析 ISO 串
    assert row["ts"].endswith("+00:00")


def test_recent_recovery_count_counts_rows_in_window(data_dir):
    a = rar.recovery_log_path(902)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(
        json.dumps({"ts": "2026-11-28T10:00:00+00:00", "worker_id": 902, "verdict": "adopted"})
        + "\n"
        + json.dumps({"ts": "2026-11-27T18:00:00+00:00", "worker_id": 902, "verdict": "adopted"})
        + "\n",
        encoding="utf-8",
    )
    # now 锚在 2026-11-28T12:00:00Z=1795867200：两行都在 24h 内（2h 前 / 18h 前）
    assert rar.recent_recovery_count(902, now=1795867200.0) == 2


def test_recent_recovery_count_ignores_rows_outside_window(data_dir):
    a = rar.recovery_log_path(903)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(
        json.dumps({"ts": "2026-11-25T10:00:00+00:00", "worker_id": 903, "verdict": "adopted"}) + "\n",
        encoding="utf-8",
    )
    assert rar.recent_recovery_count(903, now=1795867200.0) == 0


def test_recent_recovery_count_tolerates_bad_lines_and_missing_file(data_dir):
    a = rar.recovery_log_path(904)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text('not-json\n\n{"ts":"2026-11-28T10:00:00+00:00"}\n', encoding="utf-8")
    assert rar.recent_recovery_count(904, now=1795867200.0) == 1
    assert rar.recent_recovery_count(999) == 0


# ---------- 总闸：开关 + 频次止损 ----------


def test_should_auto_recover_disabled_by_flag(data_dir, monkeypatch):
    monkeypatch.setattr("utils.config_manager.get_flag", lambda key, default: False)
    ok, reason = rar.should_auto_recover(910)
    assert ok is False
    assert "开关" in reason


def test_should_auto_recover_blocked_after_three_in_window(data_dir):
    a = rar.recovery_log_path(911)
    a.parent.mkdir(parents=True, exist_ok=True)
    ts_row = json.dumps({"ts": "2026-11-28T10:00:00+00:00", "worker_id": 911, "verdict": "adopted"})
    a.write_text("\n".join([ts_row] * 3) + "\n", encoding="utf-8")
    ok, reason = rar.should_auto_recover(911, now=1795867200.0)
    assert ok is False
    assert "24h" in reason or "止损" in reason


def test_should_auto_recover_allowed_by_default(data_dir, monkeypatch):
    monkeypatch.setattr("utils.config_manager.get_flag", lambda key, default: default)
    ok, reason = rar.should_auto_recover(912)
    assert ok is True
    assert reason == ""


# ---------- best-effort 撤单 ----------

from types import SimpleNamespace
from unittest.mock import MagicMock


def _fake_trade_sync(open_orders=None, raises=False):
    ccxt = MagicMock()
    if raises:
        ccxt.fetch_open_orders.side_effect = RuntimeError("network down")
    else:
        ccxt.fetch_open_orders.return_value = open_orders or []
    ts = SimpleNamespace(exchange=SimpleNamespace(exchange=ccxt), ccxt_symbol="ETH/USDT:USDT")
    return ts, ccxt


def test_cancel_skips_without_trade_sync():
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(None, wlog)
    wlog.info.assert_called_once()


def test_cancel_fetches_and_cancels_all_orders():
    ts, ccxt = _fake_trade_sync(open_orders=[{"id": "1"}, {"id": "2"}])
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(ts, wlog)
    ccxt.fetch_open_orders.assert_called_once_with("ETH/USDT:USDT")
    assert ccxt.cancel_order.call_args_list == [
        (("1", "ETH/USDT:USDT"),),
        (("2", "ETH/USDT:USDT"),),
    ]


def test_cancel_swallows_fetch_failure():
    ts, _ = _fake_trade_sync(raises=True)
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(ts, wlog)  # 不抛即通过
    wlog.warning.assert_called()


def test_cancel_swallows_per_order_failure():
    ts, ccxt = _fake_trade_sync(open_orders=[{"id": "1"}])
    ccxt.cancel_order.side_effect = RuntimeError("order gone")
    wlog = MagicMock()
    rar.best_effort_cancel_open_orders(ts, wlog)  # 不抛即通过
    wlog.warning.assert_called()


# ---------- 处置编排 ----------


def test_try_auto_recover_rejects_non_guard_error():
    calls: list[str] = []
    ok = rar.try_auto_recover(
        920, "journal 重演失败: x", None, MagicMock(), archive_fn=lambda wid: calls.append("archive") or []
    )
    assert ok is False
    assert calls == []


def test_try_auto_recover_honors_gate(monkeypatch):
    monkeypatch.setattr("utils.config_manager.get_flag", lambda key, default: False)
    ok = rar.try_auto_recover(
        921,
        rar.RESUME_GUARD_PREFIX + "，xxxx",
        None,
        MagicMock(),
        archive_fn=lambda wid: [],
    )
    assert ok is False


def test_try_auto_recover_runs_cancel_before_archive_and_records(data_dir):
    calls: list[str] = []
    ts, ccxt = _fake_trade_sync(open_orders=[{"id": "9"}])

    def _cancel(order_id, symbol):
        calls.append("cancel")

    ccxt.cancel_order.side_effect = _cancel
    wlog = MagicMock()

    def _archive(worker_id: int) -> list[dict]:
        calls.append("archive")
        return [{"from": "a.jsonl", "to": "archive/a.jsonl"}]

    ok = rar.try_auto_recover(922, rar.RESUME_GUARD_PREFIX + "：持仓不一致", ts, wlog, archive_fn=_archive)
    assert ok is True
    assert calls == ["cancel", "archive"]  # 顺序契约：先撤单后归档
    row = json.loads(rar.recovery_log_path(922).read_text(encoding="utf-8").strip())
    assert row["verdict"] == "adopted"
    assert row["reconcile_report"] is None  # 未提供 journal_path


def test_try_auto_recover_records_reconcile_report(data_dir, tmp_path):
    journal = tmp_path / "worker_923.jsonl"
    journal.write_text("{}", encoding="utf-8")
    journal.with_suffix(".reconcile.json").write_text('{"position_breaks": 1}', encoding="utf-8")
    ok = rar.try_auto_recover(
        923,
        rar.RESUME_GUARD_PREFIX + "：x",
        None,
        MagicMock(),
        archive_fn=lambda wid: [],
        journal_path=str(journal),
    )
    assert ok is True
    row = json.loads(rar.recovery_log_path(923).read_text(encoding="utf-8").strip())
    assert row["reconcile_report"] == {"position_breaks": 1}


def test_try_auto_recover_aborts_when_archive_fails(data_dir):
    wlog = MagicMock()

    def _boom(worker_id: int) -> list[dict]:
        raise RuntimeError("mv 失败")

    ok = rar.try_auto_recover(924, rar.RESUME_GUARD_PREFIX + "：x", None, wlog, archive_fn=_boom)
    assert ok is False
    assert not rar.recovery_log_path(924).exists()  # 归档失败不记审计
    wlog.error.assert_called()
