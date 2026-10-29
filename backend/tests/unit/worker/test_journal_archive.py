"""StrategyManager.archive_journal_files 单元测试。

归档语义：把 live/rl_live 目录下 worker_{id}.jsonl（及 reconcile 报告）move 到
来源目录 archive/ 子目录，下次启动即 fresh start 重锚。报告文件当前无自动写盘方
（Rust reconcile 只返回 dict 不落盘），存在即收是防御性设计。
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from worker import strategy_manager as sm
from worker.strategy_manager import StrategyManager


class _FixedDatetime(datetime):
    """固定 now() 的 datetime 子类，替换 sm.datetime 防秒边界 flaky。"""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


TS = "20260102-030405"


@pytest.fixture
def manager() -> StrategyManager:
    # 绕过 __init__（重装配 + 全局副作用）；archive_journal_files 无实例状态依赖
    return object.__new__(StrategyManager)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "celldata"
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(d))
    return d


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sm, "datetime", _FixedDatetime)


def test_archive_live_journal_and_reconcile(manager, data_dir, fixed_now):
    live = data_dir / "live"
    live.mkdir(parents=True)
    (live / "worker_7.jsonl").write_text('{"t":1}\n', encoding="utf-8")
    (live / "worker_7.reconcile.json").write_text("{}", encoding="utf-8")

    moved = manager.archive_journal_files(7)

    by_src = {Path(m["from"]).name: Path(m["to"]) for m in moved}
    assert set(by_src) == {"worker_7.jsonl", "worker_7.reconcile.json"}
    assert by_src["worker_7.jsonl"] == live / "archive" / f"worker_7.{TS}.jsonl"
    assert by_src["worker_7.reconcile.json"] == live / "archive" / f"worker_7.reconcile.{TS}.json"
    # 文件内容真被移动（旧路径不存在、新路径可读）
    assert not (live / "worker_7.jsonl").exists()
    assert (by_src["worker_7.jsonl"]).read_text(encoding="utf-8") == '{"t":1}\n'


def test_archive_rl_journal_goes_to_rl_archive(manager, data_dir, fixed_now):
    rl = data_dir / "rl_live"
    rl.mkdir(parents=True)
    (rl / "worker_9.jsonl").write_text("rl\n", encoding="utf-8")

    moved = manager.archive_journal_files(9)

    assert len(moved) == 1
    assert Path(moved[0]["to"]) == rl / "archive" / f"worker_9.{TS}.jsonl"


def test_archive_no_candidates_raises_value_error(manager, data_dir, fixed_now):
    with pytest.raises(ValueError, match="无可归档"):
        manager.archive_journal_files(42)


def test_archive_name_conflict_appends_index(manager, data_dir, fixed_now):
    live = data_dir / "live"
    (live / "archive").mkdir(parents=True)
    # 预置同时间戳归档文件，模拟同秒内二次归档
    (live / "archive" / f"worker_3.{TS}.jsonl").write_text("old\n", encoding="utf-8")
    (live / "worker_3.jsonl").write_text("new\n", encoding="utf-8")

    moved = manager.archive_journal_files(3)

    assert Path(moved[0]["to"]) == live / "archive" / f"worker_3.{TS}_1.jsonl"
    assert (live / "archive" / f"worker_3.{TS}.jsonl").read_text(encoding="utf-8") == "old\n"
