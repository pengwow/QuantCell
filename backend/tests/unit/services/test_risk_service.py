def test_risk_service_creation():
    from services.risk_service import RiskService
    svc = RiskService()
    assert svc is not None


def test_risk_service_check_order():
    from services.risk_service import RiskService
    svc = RiskService({"max_order_value": 100000.0})

    result = svc.check_order(
        order={"symbol": "BTC-USDT", "side": "Buy", "quantity": 0.1, "price": 50000.0},
        portfolio={"cash": {"USD": 200000.0}},
    )
    assert result["passed"] is True


def test_risk_service_rejects_oversized_order():
    from services.risk_service import RiskService
    svc = RiskService({"max_order_value": 10000.0})

    result = svc.check_order(
        order={"symbol": "BTC-USDT", "side": "Buy", "quantity": 1.0, "price": 50000.0},
        portfolio={"cash": {"USD": 200000.0}},
    )
    assert result["passed"] is False
    assert result["reason"] is not None
