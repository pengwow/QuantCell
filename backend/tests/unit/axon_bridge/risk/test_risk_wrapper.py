"""axon_quant.risk 适配层测试。

验证:
1. 所有符号可从 axon_bridge.risk 直接导入
2. DefaultRiskEngine 可用 make_risk_config 构造并执行 check_order
3. RiskResult 的 allow/reject/warn 构造方法与 is_xxx 属性一致
4. CircuitBreaker 的 check_and_trigger / reset / is_active 行为正确
5. AxonQuantError 错误映射可处理 RiskError
"""

from __future__ import annotations

import pytest

# axon_quant 不可用时跳过整个模块
try:
    import axon_quant
except ImportError:
    pytest.skip("axon_quant 未安装,跳过 risk 适配层测试", allow_module_level=True)


from axon_bridge.risk import (
    CircuitBreaker,
    DefaultRiskEngine,
    RiskConfig,
    RiskError,
    RiskMetrics,
    RiskReason,
    RiskResult,
    make_circuit_breaker,
    make_order,
    make_portfolio,
    make_portfolio_with_positions,
    make_risk_config,
)

# =============================================================================
# 1. 符号重导出完整性
# =============================================================================


class TestRiskReexports:
    """确保适配层把 axon_quant.risk 的所有公共符号都暴露出来了。"""

    def test_core_classes_importable(self):
        for cls in (
            CircuitBreaker,
            DefaultRiskEngine,
            RiskConfig,
            RiskError,
            RiskMetrics,
            RiskReason,
            RiskResult,
        ):
            assert cls is not None

    def test_factory_functions_importable(self):
        for fn in (
            make_circuit_breaker,
            make_order,
            make_portfolio,
            make_portfolio_with_positions,
            make_risk_config,
        ):
            assert callable(fn)


# =============================================================================
# 2. RiskConfig / make_risk_config
# =============================================================================


class TestRiskConfig:
    def test_make_risk_config_returns_risk_config(self):
        cfg = make_risk_config(
            max_position_per_instrument=50_000.0,
            max_total_exposure=500_000.0,
            max_order_value=10_000.0,
        )
        assert isinstance(cfg, RiskConfig)

    def test_default_risk_config(self):
        """不传参数应能拿到一个默认配置,符合 make_risk_config 的默认签名。"""
        cfg = make_risk_config()
        assert isinstance(cfg, RiskConfig)


# =============================================================================
# 3. DefaultRiskEngine.check_order
# =============================================================================


class TestDefaultRiskEngine:
    def _build_engine(self) -> DefaultRiskEngine:
        """构造一个紧约束的引擎,便于快速触发 reject(若 Rust 端实现支持)。"""
        cfg = make_risk_config(
            max_position_per_instrument=1_000.0,
            max_order_value=500.0,
            max_leverage=1.0,
        )
        return DefaultRiskEngine(cfg)

    def _empty_portfolio(self) -> dict:
        """axon_quant 0.4.0 portfolio dict 必填字段: base_currency / commission_rate / cash / positions。"""
        return {
            "base_currency": "USD",
            "commission_rate": 0.001,
            "cash": {"USD": 100_000.0},
            "positions": {},
        }

    def test_engine_returns_risk_result(self):
        """无论规则是否触发,check_order 必须返回 RiskResult 实例(接口契约)。"""
        engine = self._build_engine()
        order = make_order(
            id=1,
            symbol="BTCUSDT",
            side="buy",
            type="market",
            quantity=0.001,
            price=100.0,
        )
        result = engine.check_order(order, self._empty_portfolio())
        assert isinstance(result, RiskResult)
        # 任意 result 必须有 is_allow / is_reject / is_warn 三个 bool 属性
        assert isinstance(result.is_allow, bool)
        assert isinstance(result.is_reject, bool)
        assert isinstance(result.is_warn, bool)

    def test_small_order_is_allowed(self):
        """小单应至少返回 is_allow=True(若 Rust 0.4.0 实现是 no-op,则断言 is_reject=False 即可)。"""
        engine = self._build_engine()
        order = make_order(
            id=1,
            symbol="BTCUSDT",
            side="buy",
            type="market",
            quantity=0.001,
            price=100.0,
        )
        result = engine.check_order(order, self._empty_portfolio())
        assert result.is_allow is True
        assert result.is_reject is False

    def test_engine_with_existing_positions(self):
        """带持仓的 portfolio 不能让引擎崩溃。"""
        engine = self._build_engine()
        order = make_order(
            id=1,
            symbol="BTCUSDT",
            side="buy",
            type="market",
            quantity=0.1,
            price=100.0,
        )
        portfolio = make_portfolio_with_positions(
            base_currency="USD",
            cash={"USD": 100_000.0},
            positions={"BTCUSDT": {"quantity": 0.5, "avg_cost": 3000.0}},
        )
        # portfolio dict 由工厂构造,需补 commission_rate 字段
        if isinstance(portfolio, dict) and "commission_rate" not in portfolio:
            portfolio["commission_rate"] = 0.001
        result = engine.check_order(order, portfolio)
        assert isinstance(result, RiskResult)


# =============================================================================
# 4. RiskResult 行为
# =============================================================================


class TestRiskResult:
    def test_allow_constructor(self):
        r = RiskResult.allow()
        assert r.is_allow
        assert not r.is_reject
        assert not r.is_warn

    def test_reject_constructor(self):
        # RiskResult.reject(reason: RiskReason)
        reason = RiskReason.from_dict({"kind": "position", "message": "too big"})
        r = RiskResult.reject(reason)
        assert r.is_reject
        assert not r.is_allow
        assert r.reason is not None
        assert r.reason.kind == "position"

    def test_warn_constructor(self):
        # RiskResult.warn(message: str)
        r = RiskResult.warn("near limit")
        assert r.is_warn
        assert not r.is_reject
        assert r.message == "near limit"

    def test_to_dict_roundtrip(self):
        """to_dict 应返回一个 dict,可供序列化/网络传输。"""
        reason = RiskReason.from_dict({"kind": "drawdown", "message": "test reason"})
        r = RiskResult.reject(reason)
        d = r.to_dict()
        assert isinstance(d, dict)


# =============================================================================
# 5. CircuitBreaker
# =============================================================================


class TestCircuitBreaker:
    def test_initial_state_inactive(self):
        cb = make_circuit_breaker(daily_loss_limit=1000.0, cooldown_seconds=60)
        assert isinstance(cb, CircuitBreaker)
        assert not cb.is_active

    def test_check_and_trigger_activates(self):
        """axon_quant 0.4.0 约定: daily_pnl 负数代表亏损(亏 -2000 触发 1000 阈值)。"""
        cb = make_circuit_breaker(daily_loss_limit=1000.0, cooldown_seconds=60)
        # check_and_trigger 返回 None,触发与否通过 is_active 判断
        cb.check_and_trigger(-2000.0)
        assert cb.is_active is True

    def test_check_and_trigger_under_threshold(self):
        """亏损未超阈值时不触发。"""
        cb = make_circuit_breaker(daily_loss_limit=1000.0, cooldown_seconds=60)
        cb.check_and_trigger(-500.0)  # 亏 500 < 1000
        assert not cb.is_active

    def test_reset_clears_active(self):
        cb = make_circuit_breaker(daily_loss_limit=1000.0, cooldown_seconds=60)
        cb.check_and_trigger(-2000.0)
        assert cb.is_active
        cb.reset()
        assert not cb.is_active


# =============================================================================
# 6. 错误映射
# =============================================================================


class TestErrorMapping:
    def test_risk_error_maps_to_axon_quant_error(self):
        """RiskError 应能被适配层 _errors 模块识别并转译为 403。"""
        from axon_bridge._errors import AxonQuantError, map_error

        try:
            msg = "synthetic risk failure"
            raise RiskError(msg)
        except RiskError as e:
            mapped = map_error(e)
            assert isinstance(mapped, AxonQuantError)
            # 风险类错误映射到 403(被风控拒绝)
            assert mapped.http_status == 403
            assert mapped.code == "risk_rejected"
