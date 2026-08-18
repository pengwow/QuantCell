"""Tests for worker/risk_monitor.py — RiskMonitor."""


def test_risk_monitor_creation():
    """RiskMonitor可以被创建"""
    from worker.risk_monitor import RiskMonitor

    monitor = RiskMonitor(config={"max_order_value": 100_000.0})
    assert monitor is not None


def test_risk_monitor_accepts_valid_order():
    """RiskMonitor接受有效订单"""
    from worker.risk_monitor import RiskMonitor

    monitor = RiskMonitor(config={"max_order_value": 100_000.0})

    order = {"symbol": "BTC-USDT", "side": "Buy", "quantity": 0.1, "price": 50000.0}
    portfolio = {"cash": 200000.0}

    passed = monitor.check_order(order, portfolio)
    assert passed is True
    assert len(monitor.alerts) == 0


def test_risk_monitor_rejects_and_alerts():
    """RiskMonitor拒绝超限订单并记录告警"""
    from worker.risk_monitor import RiskMonitor

    monitor = RiskMonitor(config={"max_order_value": 10_000.0})

    order = {"symbol": "BTC-USDT", "side": "Buy", "quantity": 1.0, "price": 50000.0}
    portfolio = {"cash": 200000.0}

    passed = monitor.check_order(order, portfolio)
    assert passed is False
    assert len(monitor.alerts) == 1
    assert monitor.alerts[0]["type"] == "order_rejected"


def test_risk_monitor_get_portfolio_risk():
    """RiskMonitor能获取组合风险指标"""
    from worker.risk_monitor import RiskMonitor

    monitor = RiskMonitor(config={"max_order_value": 100_000.0})

    risk = monitor.get_portfolio_risk({"cash": 200000.0})
    assert "alerts_count" in risk
    assert risk["alerts_count"] == 0
