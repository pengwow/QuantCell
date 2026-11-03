"""回测进度的单调性契约验证。

核心契约（修复多品种场景进度条回退/清零）：
1. 总体进度以历史峰值为下界，不随子进度在新品种边界被重置而回退；
2. 多品种自动下载的数据准备进度按品种区间 [idx/N, (idx+1)/N) 累加；
3. 多品种执行的执行进度按品种区间累加，品种切换不清零回退。
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from backtest.progress_tracker import get_progress_tracker
from backtest.service import BacktestService


@pytest.fixture()
def tracker():
    return get_progress_tracker()


def test_overall_progress_monotonic_when_sub_stage_resets(tracker):
    """子进度在新阶段/新品种边界被重置为 0 时，总体进度不得回退。"""
    task_id = f"t-{uuid4().hex[:8]}"
    tracker.create_progress(task_id)
    try:
        # 数据准备完成 → 总体 30%
        tracker.update_progress(task_id, "data_prep", {"progress": 100.0})
        assert tracker.get_progress(task_id).overall_progress == pytest.approx(30.0)

        # 执行阶段从 0 重新开始：总体必须守住 30%，不得回到 0 附近
        tracker.update_progress(task_id, "execution", {"progress": 0.0})
        assert tracker.get_progress(task_id).overall_progress == pytest.approx(30.0)

        # 上一品种跑满 100% 后新品种 bar 进度从 0 重来：总体守住 90%
        tracker.update_progress(task_id, "execution", {"progress": 100.0})
        assert tracker.get_progress(task_id).overall_progress == pytest.approx(90.0)
        tracker.update_progress(task_id, "execution", {"progress": 0.0})
        assert tracker.get_progress(task_id).overall_progress == pytest.approx(90.0)
    finally:
        tracker.delete_progress(task_id)


def _fake_integrity_result():
    """ensure_data_complete 成功分支只需要 result 可访问 coverage_percent。"""
    return SimpleNamespace(coverage_percent=100.0, is_complete=True, missing_ranges=[])


def test_multi_symbol_download_progress_accumulates(monkeypatch, tracker):
    """多品种自动下载：数据准备进度按品种区间累加，第二个品种开下不清零。"""
    from backtest.data_downloader import DownloadProgress

    captured = []

    class FakeDownloader:
        def ensure_data_complete(self, *, symbol, interval, start_time, end_time, crypto_type, progress_callback):
            # 模拟单个品种下载 0→40→100 的段内进度
            for pct in (0.0, 40.0, 100.0):
                p = DownloadProgress(task_id="", symbol=symbol, interval=interval)
                p.update(progress=pct)
                progress_callback(p)
            return True, _fake_integrity_result()

    monkeypatch.setattr("backtest.data_downloader.BacktestDataDownloader", FakeDownloader)

    service = BacktestService()
    task_id = f"t-{uuid4().hex[:8]}"
    # 记录每次回调后的数据准备进度
    origin_update = tracker.update_progress
    tracker.create_progress(task_id)
    try:

        def spy_update(task_id, stage, data):
            captured.append(data.get("progress"))
            return origin_update(task_id, stage, data)

        monkeypatch.setattr(tracker, "update_progress", spy_update)

        service._ensure_kline_data(
            task_id,
            {
                "symbols": ["AAA/USDT", "BBB/USDT"],
                "timeframes": ["1h"],
                "config": {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-02 00:00:00"},
            },
            tracker,
        )
    finally:
        tracker.delete_progress(task_id)

    assert captured, "必须产生下载进度回调"
    # 单调不减
    assert captured == sorted(captured), f"数据准备进度出现回退: {captured}"
    # 第二个品种的首个回调（idx=1, p=0 → 50%）必须高于第一个品种 40% 时的 20%
    assert max(captured) == pytest.approx(100.0)


def test_multi_symbol_execution_progress_accumulates(monkeypatch, tracker, tmp_path):
    """多品种执行：bar 进度按品种区间累加，品种切换不清零回退。"""
    service = BacktestService()
    service.results_dir = tmp_path
    task_id = f"t-{uuid4().hex[:8]}"

    exec_seen: list[float] = []

    class FakeEngine:
        def __init__(self, data_provider=None):
            pass

        def run_backtest(self, *, task_id=None, on_symbol_progress=None, on_bar_progress=None, **kwargs):
            # 模拟 2 品种、每品种 2 bars 的引擎回调序列
            for idx, sym in enumerate(["AAA/USDT", "BBB/USDT"]):
                on_symbol_progress(idx, 2, sym)
                for cur in (0, 1, 2):
                    on_bar_progress(cur, 2)
                    if tracker.get_progress(task_id):
                        exec_seen.append(tracker.get_progress(task_id).execution.progress)
            return {"skipped_symbols": {}}

    monkeypatch.setattr("backtest.engine_service.EventDrivenBacktestService", FakeEngine)

    service.create_task(
        strategy_name="demo",
        strategy_params={},
        symbols=["AAA/USDT", "BBB/USDT"],
        timeframes=["1h"],
        engine_type="default",
        # 不带 start_time/end_time：跳过自动下载分支，专注执行阶段
        config={"initial_cash": 10000, "interval": "1h"},
        task_id=task_id,
    )
    # 真实链路由 routes 先建进度记录再跑后台线程，这里补齐同一前置
    tracker.create_progress(task_id)
    try:
        result = service.run_backtest(task_id, tracker)
    finally:
        tracker.delete_progress(task_id)

    assert result["status"] == "completed"
    assert exec_seen, "必须产生 bar 级执行进度"
    assert exec_seen == sorted(exec_seen), f"执行进度出现回退: {exec_seen}"
    # 第一品种末尾 bar（(0+2/2)/2=50%）之后第二品种首 bar 不得低于 50%
    assert exec_seen[0] == pytest.approx(0.0)
    assert exec_seen[-1] == pytest.approx(100.0)
