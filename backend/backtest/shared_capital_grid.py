"""多品种共享资金池回测的统一时钟网格对齐。

共享资金池模式要求所有品种在**同一时钟**上推进：单个 BacktestEngine、逐网格点
`begin_bar_multi`。各品种数据起止与缺口不同，故需要把各自的 bar 序列对齐到同一
时间网格；缺失点用 `None` 占位，由 Rust 侧（`BacktestRunner::run`）前向填充
价格参与盯市，但不触发策略决策。

纯函数、无 IO、无状态，便于独立单测。
"""

from __future__ import annotations

from typing import Any


def build_shared_grid(bars_by_symbol: dict[str, list[dict[str, Any]]]) -> list[int]:
    """取各品种 bar 纳秒时间戳的并集（升序），作为共享时钟的网格。

    Args:
        bars_by_symbol: 各品种的 Rust bar dict 列表（键为 "timestamp" 纳秒整数）

    Returns:
        升序纳秒时间戳列表；全部品种为空时返回空列表
    """
    ts_set: set[int] = set()
    for bars in bars_by_symbol.values():
        for bar in bars:
            ts_set.add(int(bar["timestamp"]))
    return sorted(ts_set)


def align_bars_to_grid(
    bars: list[dict[str, Any]],
    grid: list[int],
) -> list[dict[str, Any] | None]:
    """把单品种 bar 序列对齐到网格。

    命中网格点 → 给出该 bar；该品种尚未开始（首个真实 bar 之前）或中途缺口
    → `None`。因为 `bars` 内的时间戳必然都 ≥ 首个真实 bar，所以只需一次
    「按时间戳查表」，前导与缺口自然都落成 `None`。

    Args:
        bars: 单品种 Rust bar dict 列表（时间升序）
        grid: `build_shared_grid` 产出的网格

    Returns:
        与 `grid` 等长的列表，元素为 bar dict 或 None
    """
    ts_to_bar = {int(bar["timestamp"]): bar for bar in bars}
    return [ts_to_bar.get(ts) for ts in grid]
