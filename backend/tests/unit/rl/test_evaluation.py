"""Tests for rl/evaluation.py — _compute_metrics."""

from rl.evaluation import _compute_metrics, EvaluationMetrics


def test_compute_metrics_flat_nav():
    """Flat NAV → zero PnL, zero drawdown."""
    nav = [100_000.0] * 100
    actions = [0.0] * 99
    m = _compute_metrics(nav, actions)
    assert m.total_pnl == 0.0
    assert m.total_return_pct == 0.0
    assert m.max_drawdown_pct == 0.0
    assert m.num_trades == 0


def test_compute_metrics_monotonic_increase():
    """Steadily increasing NAV → positive PnL, positive sharpe, 100% win rate."""
    nav = [100_000.0 + i * 100 for i in range(100)]
    actions = [0.5] * 99
    m = _compute_metrics(nav, actions)
    assert m.total_pnl > 0
    assert m.total_return_pct > 0
    assert m.win_rate == 1.0
    assert m.max_drawdown_pct == 0.0


def test_compute_metrics_drawdown():
    """NAV rises then drops → max_drawdown < 0."""
    nav = [100_000.0 + i * 100 for i in range(50)]
    nav += [nav[-1] - i * 200 for i in range(1, 51)]
    actions = [0.5] * 99
    m = _compute_metrics(nav, actions)
    assert m.total_pnl < 0
    assert m.max_drawdown_pct < 0


def test_compute_metrics_trade_count():
    """Position changes > 0.01 count as trades."""
    nav = [100_000.0 + i for i in range(100)]
    # alternating buy/sell: 0.5 → -0.5 = change of 1.0 each
    actions = [0.5 if i % 2 == 0 else -0.5 for i in range(99)]
    m = _compute_metrics(nav, actions)
    assert m.num_trades == 98  # 98 changes of 1.0


def test_compute_metrics_profit_factor():
    """Mix of positive and negative returns → finite profit_factor."""
    import math
    nav = [100.0]
    for i in range(50):
        nav.append(nav[-1] * (1.01 if i % 3 != 0 else 0.99))
    actions = [0.0] * 49
    m = _compute_metrics(nav, actions)
    assert m.profit_factor > 0
    assert not math.isinf(m.profit_factor)


def test_compute_metrics_short_nav():
    """NAV with < 2 entries → returns default metrics."""
    m = _compute_metrics([100_000.0], [])
    assert m.total_pnl == 0.0
    assert m.sharpe_ratio == 0.0


def test_evaluate_metrics_dataclass():
    """EvaluationMetrics defaults."""
    m = EvaluationMetrics()
    assert m.total_pnl == 0.0
    assert m.sharpe_ratio == 0.0
    assert m.num_trades == 0
