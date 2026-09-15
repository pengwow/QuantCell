"""Tests for backtest/walk_forward.py — WalkForwardService."""

import pandas as pd


def test_walk_forward_service_creation():
    """WalkForwardService可以被创建"""
    from backtest.walk_forward import WalkForwardService

    wf = WalkForwardService()
    assert wf is not None


def test_walk_forward_rolling_mode():
    """WalkForwardService支持rolling模式"""
    from backtest.walk_forward import WalkForwardService

    wf = WalkForwardService()

    data = pd.DataFrame(
        {
            "close": range(100, 200),
            "volume": [1000] * 100,
        }
    )

    result = wf.validate(
        strategy_fn=None,
        data=data,
        n_splits=3,
        train_ratio=0.7,
        mode="rolling",
    )
    assert "splits" in result
    assert len(result["splits"]) == 3
    assert result["mode"] == "rolling"


def test_walk_forward_expanding_mode():
    """WalkForwardService支持expanding模式"""
    from backtest.walk_forward import WalkForwardService

    wf = WalkForwardService()

    data = pd.DataFrame(
        {
            "close": range(100, 200),
            "volume": [1000] * 100,
        }
    )

    result = wf.validate(
        strategy_fn=None,
        data=data,
        n_splits=3,
        train_ratio=0.7,
        mode="expanding",
    )
    assert "splits" in result
    assert len(result["splits"]) > 0
    assert result["mode"] == "expanding"


def _assert_no_leakage(split: dict) -> None:
    """断言单个切分无前视泄漏:训练区间终点不越过测试区间起点。"""
    assert split["train_end"] <= split["test_start"], (
        f"train/test 区间重叠: train_end={split['train_end']} > test_start={split['test_start']}"
    )


def test_walk_forward_rolling_no_leakage():
    """rolling 模式 train/test 无重叠(报告 E3 无泄漏契约)。"""
    from backtest.walk_forward import WalkForwardService

    wf = WalkForwardService()
    data = pd.DataFrame({"close": range(100, 300), "volume": [1000] * 200})

    result = wf.validate(
        strategy_fn=None,
        data=data,
        n_splits=4,
        train_ratio=0.7,
        mode="rolling",
    )
    for split in result["splits"]:
        _assert_no_leakage(split)


def test_walk_forward_expanding_no_leakage():
    """expanding 模式训练窗口单调扩张,且训练区间同样不包含测试区间。"""
    from backtest.walk_forward import WalkForwardService

    wf = WalkForwardService()
    data = pd.DataFrame({"close": range(100, 300), "volume": [1000] * 200})

    result = wf.validate(
        strategy_fn=None,
        data=data,
        n_splits=4,
        train_ratio=0.7,
        mode="expanding",
    )
    prev_train_end = 0
    for split in result["splits"]:
        _assert_no_leakage(split)
        # expanding:train_start 固定为 0 且 train_end 单调扩张
        assert split["train_start"] == 0
        assert split["train_end"] >= prev_train_end
        prev_train_end = split["train_end"]
