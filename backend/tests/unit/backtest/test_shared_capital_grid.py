"""共享资金池网格对齐纯函数单测（无 IO、无状态）。"""

from backtest.shared_capital_grid import align_bars_to_grid, build_shared_grid


def _bar(ts: int, close: float) -> dict:
    return {
        "timestamp": ts,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }


def test_build_shared_grid_is_sorted_union():
    bars = {
        "BTC/USDT": [_bar(10, 100.0), _bar(30, 101.0)],
        "ETH/USDT": [_bar(20, 20.0), _bar(30, 21.0)],
    }
    assert build_shared_grid(bars) == [10, 20, 30]


def test_build_shared_grid_handles_empty_symbol():
    bars = {"BTC/USDT": [_bar(10, 100.0)], "ETH/USDT": []}
    assert build_shared_grid(bars) == [10]


def test_align_bars_fills_holes_with_none():
    grid = [10, 20, 30]
    bars = [_bar(10, 100.0), _bar(30, 101.0)]
    aligned = align_bars_to_grid(bars, grid)
    assert aligned[0]["close"] == 100.0
    assert aligned[1] is None  # 缺口 → None（Rust 侧前向填充价格）
    assert aligned[2]["close"] == 101.0


def test_align_bars_leading_none_before_first_bar():
    grid = [10, 20, 30]
    bars = [_bar(30, 101.0)]  # 品种 30 才开始交易
    aligned = align_bars_to_grid(bars, grid)
    assert aligned[0] is None and aligned[1] is None
    assert aligned[2]["close"] == 101.0


def test_align_bars_empty_series_all_none():
    assert align_bars_to_grid([], [10, 20]) == [None, None]
