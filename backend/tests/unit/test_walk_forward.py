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
