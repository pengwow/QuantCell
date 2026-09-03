"""Tests for rl/evaluation.py — _compute_metrics."""

from rl.evaluation import EvaluationMetrics, _compute_metrics


def test_compute_metrics_flat_nav():
    """Flat NAV → zero PnL, zero drawdown."""
    nav = [100_000.0] * 100
    m = _compute_metrics(nav, 0)
    assert m.total_pnl == 0.0
    assert m.total_return_pct == 0.0
    assert m.max_drawdown_pct == 0.0
    assert m.num_trades == 0


def test_compute_metrics_monotonic_increase():
    """Steadily increasing NAV → positive PnL, positive sharpe, 100% win rate."""
    nav = [100_000.0 + i * 100 for i in range(100)]
    m = _compute_metrics(nav, 3)
    assert m.total_pnl > 0
    assert m.total_return_pct > 0
    assert m.win_rate == 1.0
    assert m.max_drawdown_pct == 0.0
    assert m.num_trades == 3


def test_compute_metrics_drawdown():
    """NAV rises then drops → max_drawdown < 0."""
    nav = [100_000.0 + i * 100 for i in range(50)]
    nav += [nav[-1] - i * 200 for i in range(1, 51)]
    m = _compute_metrics(nav, 0)
    assert m.total_pnl < 0
    assert m.max_drawdown_pct < 0


def test_compute_metrics_num_trades():
    """num_trades 直接透传到结果（真实成交笔数由环境 info 提供，不再从动作序列推导）。"""
    nav = [100_000.0 + i for i in range(100)]
    m = _compute_metrics(nav, 42)
    assert m.num_trades == 42


def test_compute_metrics_profit_factor():
    """Mix of positive and negative returns → finite profit_factor."""
    import math

    nav = [100.0]
    for i in range(50):
        nav.append(nav[-1] * (1.01 if i % 3 != 0 else 0.99))
    m = _compute_metrics(nav, 0)
    assert m.profit_factor > 0
    assert not math.isinf(m.profit_factor)


def test_compute_metrics_short_nav():
    """NAV with < 2 entries → returns default metrics."""
    m = _compute_metrics([100_000.0], 0)
    assert m.total_pnl == 0.0
    assert m.sharpe_ratio == 0.0


def test_evaluate_metrics_dataclass():
    """EvaluationMetrics defaults."""
    m = EvaluationMetrics()
    assert m.total_pnl == 0.0
    assert m.sharpe_ratio == 0.0
    assert m.num_trades == 0
