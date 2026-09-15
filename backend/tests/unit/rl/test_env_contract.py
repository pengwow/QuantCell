"""P1 RL / gym 环境契约测试。

覆盖报告 E1「TradingEnv / BacktestEnv(gym) 契约」:
- BacktestEnv: 单 leg 观测维度 64、action ∈ [-1,1]、reset 透传 seed
- MultiLegBacktestEnv: 少于 2 leg 拒绝
- 换挡点:行动由 native 提供,这里只锁定稳定契约,不深入训练
"""

from __future__ import annotations

import numpy as np
import pytest

BACKENV = pytest.importorskip("axon_quant.env")


def _make_spot():
    from axon_quant.backtest import spot_instrument

    return spot_instrument("BTC", "USDT")


def test_backtest_env_obs_dim_64() -> None:
    """单 leg BacktestEnv 观测 = Box(64,),与报告 OBS_DIM_SINGLE_LEG=64 对齐。"""
    env = BACKENV.BacktestEnv(instrument=_make_spot(), initial_cash=100_000.0, seed=1)
    assert env.observation_space.shape == (64,)
    obs, info = env.reset()
    assert obs.shape == (64,)
    assert info["nav"] == 100_000.0


def test_backtest_env_action_bounded_neg1_1() -> None:
    """action_space ∈ [-1, 1],与 env.py 内注释的归一化调仓量语义一致。"""
    env = BACKENV.BacktestEnv(instrument=_make_spot(), initial_cash=100_000.0, seed=1)
    low = float(env.action_space.low[0])
    high = float(env.action_space.high[0])
    assert low == -1.0
    assert high == 1.0


def test_backtest_env_step_returns_gym_5_tuple() -> None:
    """step 返回 gym 标准 5 元组 (obs, reward, terminated, truncated, info)。"""
    env = BACKENV.BacktestEnv(instrument=_make_spot(), initial_cash=100_000.0, seed=1)
    env.reset()
    _obs, reward, terminated, truncated, info = env.step(np.array([0.5], dtype=np.float32))
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert "nav" in info


def test_backtest_env_reset_with_seed() -> None:
    """reset(seed=...) 透传,不回抛出;两次同 seed 应产出相同初态。"""
    a = BACKENV.BacktestEnv(instrument=_make_spot(), initial_cash=100_000.0, seed=7)
    b = BACKENV.BacktestEnv(instrument=_make_spot(), initial_cash=100_000.0, seed=7)
    obs_a, _ = a.reset(seed=7)
    obs_b, _ = b.reset(seed=7)
    np.testing.assert_array_equal(obs_a, obs_b)


def test_multileg_env_requires_two_legs() -> None:
    """MultiLegBacktestEnv 至少需要 2 个 leg,否则明确报错。"""
    from axon_quant.env import LegSpec, MultiLegBacktestEnv

    ins = _make_spot()
    with pytest.raises(ValueError):
        MultiLegBacktestEnv(legs=[LegSpec(instrument=ins, target_qty_scale=1.0)])


def test_trading_env_surface_contract() -> None:
    """native TradingEnv 通过 axon_bridge 暴露,构造可用即将市场数据列表。"""
    import warnings

    from axon_bridge import TradingEnv

    warnings.filterwarnings("ignore", category=UserWarning)
    env = TradingEnv(
        config={},
        action_space={"type": "discrete", "n_quantity_bins": 5},
        market_data=[
            {
                "timestamp": 1_700_000_000_000,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 100.0,
            }
        ],
        reward="pnl",
    )
    obs = env.reset()
    assert len(obs) > 0
