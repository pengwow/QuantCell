"""RL model evaluation — compute OOS trading metrics from NAV history."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class EvaluationMetrics:
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    profit_factor: float = 0.0


def evaluate_model(model, env) -> EvaluationMetrics:
    """Run a trained SB3 model on env, collect NAV trajectory, compute metrics."""
    obs, reset_info = env.reset()
    initial_nav = reset_info.get("portfolio_value", 100_000.0)
    nav_history = [initial_nav]
    actions_taken = []
    done = False

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        nav = info.get("portfolio_value", info.get("nav", 0.0))
        nav_history.append(nav)
        actions_taken.append(float(action[0]) if hasattr(action, '__len__') else float(action))

    if len(nav_history) < 2:
        return EvaluationMetrics()

    return _compute_metrics(nav_history, actions_taken)


def _compute_metrics(nav_history: list[float], actions: list[float]) -> EvaluationMetrics:
    nav = np.array(nav_history, dtype=np.float64)
    returns = np.diff(nav) / nav[:-1]
    returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)

    total_pnl = float(nav[-1] - nav[0])
    total_return_pct = (total_pnl / nav[0] * 100) if nav[0] != 0 else 0.0

    if len(returns) > 1 and np.std(returns) > 0:
        sharpe_ratio = float(np.mean(returns) / np.std(returns) * math.sqrt(252))
    else:
        sharpe_ratio = 0.0

    peak = np.maximum.accumulate(nav)
    drawdowns = (peak - nav) / np.where(peak > 0, peak, 1.0)
    max_drawdown_pct = float(-np.max(drawdowns) * 100)

    positive_steps = np.sum(returns > 0)
    win_rate = float(positive_steps / len(returns)) if len(returns) > 0 else 0.0

    pos_returns = returns[returns > 0]
    neg_returns = returns[returns < 0]
    if len(neg_returns) > 0 and np.sum(np.abs(neg_returns)) > 0:
        profit_factor = float(np.sum(pos_returns) / np.sum(np.abs(neg_returns)))
    else:
        profit_factor = float('inf') if len(pos_returns) > 0 else 0.0

    actions_arr = np.array(actions, dtype=np.float64)
    position_changes = np.abs(np.diff(actions_arr))
    num_trades = int(np.sum(position_changes > 0.01))

    return EvaluationMetrics(
        total_pnl=round(total_pnl, 2),
        total_return_pct=round(total_return_pct, 4),
        sharpe_ratio=round(sharpe_ratio, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        win_rate=round(win_rate, 4),
        num_trades=num_trades,
        profit_factor=round(profit_factor, 4),
    )
