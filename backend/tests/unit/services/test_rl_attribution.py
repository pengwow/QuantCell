"""内核 vs TradingEnv 口径差异的四类归因（`attribute_engine_diff`）。

覆盖：
1. 两口径成本一致 → `cost.ok` 为 True，残差等于总差；
2. 成本不一致 → `cost.ok` 为 False 且带 `error`（这是 bug，不是口径差异）；
3. 资金费只有内核建模；
4. 端到端：同一份 20 根 bar + 确定性动作跑两条真实口径，归因自身自洽。

不训练真模型、不请求网络：SB3 侧用固定输出的假模型。
"""

from __future__ import annotations

import pandas as pd
import pytest

from services.rl_service import attribute_engine_diff


def test_cost_must_match():
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0},
        kernel={"total_pnl": 1_200.0, "fees": 10.0},
    )

    assert report["cost"]["ok"] is True
    assert "error" not in report
    assert report["cost"]["diff"] == 0.0
    assert report["total_pnl"]["diff"] == 200.0
    # 成本一致、无资金费、无单独测得的动作差 → 残差就是总差
    assert report["matching"]["residual"] == 200.0


def test_cost_mismatch_is_flagged():
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0},
        kernel={"total_pnl": 1_190.0, "fees": 20.0},
    )

    assert report["cost"]["ok"] is False
    assert report["error"] == "成本模型不一致"
    assert report["cost"]["diff"] == 10.0


def test_funding_only_in_kernel():
    """TradingEnv 不建模资金费：内核的资金费单独成类，并从残差里扣掉。"""
    report = attribute_engine_diff(
        trading_env={"total_pnl": 1_000.0, "fees": 10.0},
        kernel={"total_pnl": 1_005.0, "fees": 10.0, "funding": 5.0},
    )

    assert report["cost"]["ok"] is True
    assert report["funding"] == {"kernel": 5.0}
    assert report["action"]["diff"] == 0.0
    # 总差 5 全部由资金费解释，撮合层没有剩余
    assert report["matching"]["residual"] == pytest.approx(0.0)


def test_e2e_kernel_vs_trading_env_attribution(monkeypatch, tmp_path):
    """端到端：同一份 20 根 bar、同一个确定性动作跑两条真实口径。

    归因本身必须自洽（四类还原总差、资金费为 0）。`cost.ok` 在这里是 **False**：
    两条口径的默认成本模型本就不一致（`TradingEnv` `transaction_cost=0.0001`
    加滑点，内核 taker 0.001），而且内核逐 bar 重平衡、`TradingEnv` 有 1% 的
    `min_trade_threshold`，成交量也不同。这正是归因要暴露的口径差 —— 想让
    `cost.ok` 判 True，得先对齐费率与重平衡口径，而不是放宽容差。
    """
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    import numpy as np

    from rl.evaluation import evaluate_model
    from services.rl_service import GymnasiumWrapper, RLService

    if GymnasiumWrapper is None:
        pytest.skip("gymnasium 不可用")

    n = 20
    # 时间列走 DatetimeIndex（与 `BacktestDataProvider` 产出同形）：`create_env`
    # 只看列、不看 index，会给 TradingEnv 补 `range(n)` 的整数时间戳
    data = pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [10.0] * n,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
    )

    class FixedModel:
        """确定性策略：每根 bar 都要求 20% 权益占比。"""

        def predict(self, obs, deterministic=True):
            return np.array([0.2], dtype=np.float32), None

    svc = RLService()
    monkeypatch.setattr(svc, "load_model", lambda path: FixedModel())

    kernel_result = svc._run_kernel_backtest(str(tmp_path / "demo_ppo.zip"), data, "BTCUSDT", "1h", 100_000.0)

    wrapped_env = GymnasiumWrapper(svc.create_env(data, initial_capital=100_000.0))
    try:
        metrics = evaluate_model(FixedModel(), wrapped_env)
        # 累计手续费由环境 info 给出（evaluate_model 只回 PnL/风险指标）
        env_fees = float(wrapped_env._env.info["transaction_costs"])
    finally:
        wrapped_env.close()

    report = attribute_engine_diff(
        trading_env={"total_pnl": metrics.total_pnl, "fees": env_fees},
        kernel={
            "total_pnl": kernel_result["total_pnl"],
            "fees": kernel_result["total_fees"],
            "funding": kernel_result["total_funding"],
        },
    )

    assert env_fees > 0.0, "固定 0.2 占比必须真的成交"
    assert kernel_result["num_trades"] >= 1
    assert report["funding"]["kernel"] == 0.0, "现货口径没有资金费"
    assert report["total_pnl"]["diff"] == pytest.approx(kernel_result["total_pnl"] - metrics.total_pnl)
    # 四类归因自洽：-成本差 + 资金费 + 动作差 + 残差 == 总差
    assert report["total_pnl"]["diff"] == pytest.approx(
        -report["cost"]["diff"]
        + report["funding"]["kernel"]
        + report["action"]["diff"]
        + report["matching"]["residual"]
    )
    assert report["cost"]["ok"] is False
    assert report["error"] == "成本模型不一致"
