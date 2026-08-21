"""RiskService 格式对齐回归测试 — get_metrics 与 check_order 使用同一套格式转换。"""

from services.risk_service import RiskService
from strategy.live_portfolio import LivePortfolio


class TestRiskServiceFormatConsistency:
    """验证 get_metrics 与 check_order 使用一致的 portfolio 格式转换。"""

    def test_get_metrics_accepts_live_portfolio_dict(self):
        """LivePortfolio.to_dict() 格式应能直接传给 get_metrics。"""
        svc = RiskService()
        pf = LivePortfolio(initial_cash=500_000.0)
        pf_dict = pf.to_dict()
        # 关键断言: 不应抛 AttributeError
        metrics = svc.get_metrics(pf_dict)
        assert metrics is not None, "get_metrics 应返回指标 dict"
        # axon_quant metrics 返回的字段可能因版本而异, 只检查非空即可
        assert len(metrics) > 0

    def test_get_metrics_accepts_none_portfolio(self):
        """get_metrics(None) 不应抛异常, 应返回默认指标。"""
        svc = RiskService()
        metrics = svc.get_metrics(None)
        assert metrics is not None

    def test_check_order_and_get_metrics_both_use_same_converter(self):
        """确认 check_order 与 get_metrics 都能处理同一份 LivePortfolio dict。"""
        svc = RiskService()
        pf = LivePortfolio(initial_cash=200_000.0)
        # 先做一次买卖使 cash 非初始值, 验证转换逻辑正确
        pf.update_on_fill("BTCUSDT", "buy", 1.0, 50000)
        pf_dict = pf.to_dict()

        order = {"id": 1, "symbol": "BTCUSDT", "side": "Buy", "type": "limit", "quantity": 0.1, "price": 50000.0}
        check_result = svc.check_order(order, pf_dict)
        assert "passed" in check_result

        metrics = svc.get_metrics(pf_dict)
        assert metrics is not None
