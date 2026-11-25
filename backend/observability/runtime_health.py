"""首页「系统状态」卡的业务链路读数（进程内环形缓冲）。

三个口径都来自真实调用点，不做推算：
- 引擎：worker 泵每轮 tick 的墙钟耗时（`strategy_manager` 的 live tick / paper 拉取轮），
  与 Prometheus 的 qc_worker_pump_round_seconds 同源，只是这里保留最近 N 次用于算均值/p95；
- LLM：`axon_bridge.llm.chat_to_dict` / `accumulate_stream` 每次请求的耗时与错误分类
  （429 走 `classify_llm_error` → "rate_limit"）；
- 交易所探测延迟与行情库覆盖度不在这里：前者写回 `SystemService` 的探测缓存，
  后者按需查库（`SystemService.get_data_source_status`）。

ponytail: 环形缓冲是进程内状态，uvicorn 单进程部署下与真实一致；多 worker 部署时
每个进程各记各的（首页只会看到处理该请求的进程），升级路径是把缓冲换成
Prometheus 指标或 Redis，键名不变。
"""

from __future__ import annotations

import math
import time
from collections import deque
from threading import Lock
from typing import Any

# 引擎：最近 240 轮泵 tick（1s 节拍约 4 分钟窗口）
_ENGINE_SAMPLES = 240
# LLM：最近 5 分钟窗口，最多留 500 次调用（防爆内存）
_LLM_WINDOW_SECONDS = 300.0
_LLM_SAMPLES = 500

_engine_ticks: deque[float] = deque(maxlen=_ENGINE_SAMPLES)
_llm_calls: deque[tuple[float, float, bool, str | None]] = deque(maxlen=_LLM_SAMPLES)
_engine_last_at: float | None = None
_llm_last_at: float | None = None
_lock = Lock()


def _percentile(sorted_values: list[float], q: float) -> float:
    """最近秩分位数（q=0.95 → 第 95 百分位），样本少时退回最大值。"""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[idx]


def record_engine_tick(seconds: float) -> None:
    """记录一轮泵 tick 的墙钟耗时（秒）。调用点已在 finally 里，异常路径同样计入。"""
    global _engine_last_at
    if seconds < 0:
        return
    with _lock:
        _engine_ticks.append(seconds)
        _engine_last_at = time.time()


def record_llm_call(seconds: float, *, error_kind: str | None = None) -> None:
    """记录一次 LLM 请求。error_kind 取 `classify_llm_error` 的分类；None 表示成功。"""
    global _llm_last_at
    if seconds < 0:
        return
    with _lock:
        _llm_calls.append((time.time(), seconds, error_kind is None, error_kind))
        _llm_last_at = time.time()


def engine_stats() -> dict[str, Any]:
    """引擎泵读数：均值/p95/样本数/最后时间（epoch 秒）。空窗时 avg_ms 为 None。"""
    with _lock:
        samples = list(_engine_ticks)
        last_at = _engine_last_at
    if not samples:
        return {"avg_ms": None, "p95_ms": None, "samples": 0, "last_at": None}
    ms = sorted(v * 1000.0 for v in samples)
    return {
        "avg_ms": round(sum(ms) / len(ms), 2),
        "p95_ms": round(_percentile(ms, 0.95), 2),
        "samples": len(ms),
        "last_at": last_at,
    }


def llm_stats(now: float | None = None) -> dict[str, Any]:
    """LLM 近 5 分钟读数：调用数 / p95 / 429 次数 / 其它失败次数 / 最后时间。

    没有调用时 p95_ms 为 None，前端显示「—」而不是 0。
    """
    current = time.time() if now is None else now
    cutoff = current - _LLM_WINDOW_SECONDS
    with _lock:
        recent = [c for c in _llm_calls if c[0] >= cutoff]
        last_at = _llm_last_at
    if not recent:
        return {
            "window_seconds": int(_LLM_WINDOW_SECONDS),
            "calls": 0,
            "p95_ms": None,
            "rate_limit": 0,
            "failed": 0,
            "last_at": last_at,
        }
    durations = sorted(v * 1000.0 for _, v, _, _ in recent)
    return {
        "window_seconds": int(_LLM_WINDOW_SECONDS),
        "calls": len(recent),
        "p95_ms": round(_percentile(durations, 0.95), 0),
        "rate_limit": sum(1 for _, _, ok, kind in recent if not ok and kind == "rate_limit"),
        "failed": sum(1 for _, _, ok, _ in recent if not ok),
        "last_at": last_at,
    }


def reset_for_tests() -> None:
    global _engine_last_at, _llm_last_at
    with _lock:
        _engine_ticks.clear()
        _llm_calls.clear()
        _engine_last_at = None
        _llm_last_at = None
