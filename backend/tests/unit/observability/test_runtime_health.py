"""首页「系统状态」业务读数的进程内聚合（observability/runtime_health.py）。

守护三件事：空窗必须回 None 而不是 0（前端显示「—」）、分位数取最近秩、
LLM 窗口按近 5 分钟裁剪且 429 单独计数。
"""

from __future__ import annotations

import time

import pytest

from observability import runtime_health as rh


@pytest.fixture(autouse=True)
def _clean():
    rh.reset_for_tests()
    yield
    rh.reset_for_tests()


def test_engine_stats_empty_returns_none_not_zero():
    stats = rh.engine_stats()
    assert stats["avg_ms"] is None and stats["p95_ms"] is None
    assert stats["samples"] == 0


def test_engine_stats_mean_and_p95():
    for ms in (2.0, 4.0, 10.0, 20.0):
        rh.record_engine_tick(ms / 1000.0)
    stats = rh.engine_stats()
    assert stats["samples"] == 4
    assert stats["avg_ms"] == 9.0
    # 最近秩：ceil(0.95*4)-1 = 3 → 最大值
    assert stats["p95_ms"] == 20.0
    assert stats["last_at"] is not None


def test_llm_stats_window_and_rate_limit():
    now = time.time()
    rh.record_llm_call(0.30, error_kind=None)
    rh.record_llm_call(0.10, error_kind=None)
    rh.record_llm_call(0.50, error_kind="rate_limit")
    rh.record_llm_call(0.20, error_kind="timeout")
    stats = rh.llm_stats(now=now)
    assert stats["calls"] == 4
    assert stats["rate_limit"] == 1
    assert stats["failed"] == 2
    # 最近秩：ceil(0.95*4)-1 = 3 → 500ms（最大值）
    assert stats["p95_ms"] == 500.0

    # 窗口外（>5 分钟）全部滚出 → 空窗回 None
    later = rh.llm_stats(now=now + 301)
    assert later["calls"] == 0 and later["p95_ms"] is None
