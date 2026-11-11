"""RL model evaluation — 门面转发 axon_quant.rl 评估设施。

指标计算设施（env 逐 step 回放 + NAV 统计口径：√252 年化 / 999.99 哨兵 /
round 精度）已于 2026-11-11 下沉到 `axon_quant.rl.evaluation`，数值口径逐行
对齐原实现；backend 保留 `evaluate_model` 签名与 `EvaluationMetrics` dataclass
作为编排契约，门面仅做 SB3 模型适配与 dict→dataclass 转换。
"""

from __future__ import annotations

from dataclasses import dataclass

from axon_quant.rl import evaluate


@dataclass
class EvaluationMetrics:
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    profit_factor: float = 0.0
    # 成交名义总额（Σ|price×qty|），与内核口径对账时把手续费折算成费率用
    turnover: float = 0.0


def evaluate_model(model, env, transaction_cost: float | None = None) -> EvaluationMetrics:
    """Run a trained SB3 model on env, collect NAV trajectory, compute metrics.

    Args:
        transaction_cost: 环境实际使用的费率（`TradingEnv` 的 `transaction_cost`）。
            传入时用 `transaction_costs / transaction_cost` 反推成交名义总额；
            `None` 表示调用方不关心费率口径，`turnover` 记 0。

            这里**不用逐笔成交累加**，因为 `TradingEnv` 的 `info` 只暴露累计
            `transaction_costs`，没有逐笔明细；而该环境的成本定义就是
            `notional × fee_rate`（见 axon-rl `executor` 的 `cost_model.fee`），
            所以反推是恒等式，不是估算。
    """
    # SB3 的 predict 返回 (action, state)；设施协议是 predict_fn(obs) -> action，取 [0]
    raw = evaluate(
        lambda obs: model.predict(obs, deterministic=True)[0],
        env,
        transaction_cost=transaction_cost,
    )
    return EvaluationMetrics(**raw)
