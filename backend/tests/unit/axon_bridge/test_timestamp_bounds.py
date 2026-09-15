"""P1 to_ns_timestamp 边界契约测试。

覆盖报告 6.2「to_ns_timestamp 魔法区间(1e9/1e12/1e15/1e18) 跨单位边界」:
每个档位的"恰好等于"边界必须落在正确单位,不能因 > 落入低一档被错误放大。
回归项: 实测修复了 1e18(纳秒)×1000、1e15(微秒)×1e6、1e12(毫秒)×1e9 越档问题。
"""

from __future__ import annotations

from datetime import datetime

from axon_bridge import to_ns_timestamp


def test_nanosecond_passthrough() -> None:
    """原生纳秒(2024 年 ≈ 1.7e18 与阈值 1e18)应原样返回。"""
    assert to_ns_timestamp(1_700_000_000_000_000_000) == 1_700_000_000_000_000_000


def test_microsecond_conversion() -> None:
    """微秒 × 1000 → 纳秒(1.7e15 µs ≈ 2024 年)。"""
    assert to_ns_timestamp(1_700_000_000_000_000) == 1_700_000_000_000_000_000


def test_millisecond_conversion() -> None:
    """毫秒 × 1e6 → 纳秒(1.7e12 ms ≈ 2024 年)。"""
    assert to_ns_timestamp(1_700_000_000_000) == 1_700_000_000_000_000_000


def test_second_conversion() -> None:
    """秒 × 1e9 → 纳秒(1.7e9 s ≈ 2024 年)。"""
    assert to_ns_timestamp(1_700_000_000) == 1_700_000_000_000_000_000


def test_low_second_boundary() -> None:
    """低于 1e9 的秒级小值也走 × 1e9(1970s 数据)。"""
    assert to_ns_timestamp(123) == 123_000_000_000


def test_exact_ns_boundary_not_amplified() -> None:
    """1e18 ns 恰好等于阈值:应原样返回,不能被 ×1000 放大成 1e21。
    修复前该值落入微秒档误放大(报告 6.2 高风险点回归)。
    """
    assert to_ns_timestamp(1_000_000_000_000_000_000) == 1_000_000_000_000_000_000


def test_exact_us_boundary_not_amplified() -> None:
    """1e15 µs 恰好等于阈值:应 ×1000 → 1e18,不能被 ×1e6。"""
    assert to_ns_timestamp(1_000_000_000_000_000) == 1_000_000_000_000_000_000


def test_exact_ms_boundary_not_amplified() -> None:
    """1e12 ms 恰好等于阈值:应 ×1e6 → 1e18,不能被 ×1e9。"""
    assert to_ns_timestamp(1_000_000_000_000) == 1_000_000_000_000_000_000


def test_datetime_and_iso_string() -> None:
    """datetime 对象与 ISO 字符串统一转纳秒。"""
    dt = datetime(2024, 1, 1, 0, 0, 0)
    expected = int(dt.timestamp() * 1e9)
    assert to_ns_timestamp(dt) == expected
    assert to_ns_timestamp("2024-01-01T00:00:00") == expected


def test_invalid_inputs_return_zero() -> None:
    """非法字符串 / None 返回 0,不抛异常。"""
    assert to_ns_timestamp("not-a-date") == 0
    assert to_ns_timestamp(None) == 0
    assert to_ns_timestamp({}) == 0
