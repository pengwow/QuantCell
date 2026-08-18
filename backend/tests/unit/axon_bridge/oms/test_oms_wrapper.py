"""axon_quant.oms 适配层测试。

验证:
1. 顶层符号 (Order / OrderManager / OrderType / Side / Portfolio / Position / OmsError) 可导入
2. 工厂函数 market_order / limit_order / make_order_status 可用
3. OrderManager.submit → update_status → add_fill 端到端走通(参考 oms.py docstring)
4. Portfolio.deposit 行为正确
5. OmsError 错误映射到 409
"""

from __future__ import annotations

import pytest

try:
    import axon_quant
except ImportError:
    pytest.skip("axon_quant 未安装,跳过 oms 适配层测试", allow_module_level=True)


from axon_bridge.oms import (
    OmsError,
    Order,
    OrderManager,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    Side,
    limit_order,
    make_order_status,
    market_order,
)

# =============================================================================
# 1. 符号重导出
# =============================================================================


class TestOmsReexports:
    def test_classes_importable(self):
        for cls in (
            OmsError,
            Order,
            OrderManager,
            OrderStatus,
            OrderType,
            Portfolio,
            Position,
            Side,
        ):
            assert cls is not None

    def test_factories_importable(self):
        for fn in (limit_order, make_order_status, market_order):
            assert callable(fn)

    def test_enum_values(self):
        """OrderType / Side 的常用枚举值必须存在。"""
        assert OrderType.Market is not None
        assert OrderType.Limit is not None
        assert Side.Buy is not None
        assert Side.Sell is not None


# =============================================================================
# 2. 工厂函数
# =============================================================================


class TestOrderFactories:
    def test_market_order_returns_order(self):
        order = market_order(symbol="BTCUSDT", side="Buy", quantity=0.1)
        assert isinstance(order, Order)
        d = order.to_dict()
        assert d["symbol"] == "BTCUSDT"
        assert d["side"] in ("Buy", "buy")

    def test_limit_order_returns_order(self):
        order = limit_order(symbol="BTCUSDT", side="Sell", quantity=0.5, price=50_000.0)
        assert isinstance(order, Order)
        d = order.to_dict()
        assert d["symbol"] == "BTCUSDT"
        # 内部以 Decimal 字符串存,50_000.0 序列化为 "50000.0"
        assert d["price"] == "50000.0"

    def test_order_to_dict_uses_decimal_strings(self):
        """quantity/price 字段在 to_dict 中以字符串形式返回(Decimal 精度)。"""
        order = market_order(symbol="BTCUSDT", side="Buy", quantity=0.1)
        d = order.to_dict()
        assert d["quantity"] == "0.1"


# =============================================================================
# 3. OrderManager 端到端
# =============================================================================


class TestOrderManager:
    """参考 axon_quant.oms docstring 的标准 4 步流程。"""

    def test_full_lifecycle(self):
        """submit → Acknowledged → Filled 完整路径。"""
        mgr = OrderManager()
        mgr.deposit("USDT", 100_000.0)

        # 1) 提交订单
        oid = mgr.submit(limit_order("BTCUSDT", "Buy", 0.1, 50_000.0, idempotency_key="k1"))
        assert isinstance(oid, str) and len(oid) > 0
        assert mgr.active_count() == 1
        assert mgr.get_order_status(oid).kind == "Submitted"

        # 2) 状态机: Submitted -> Acknowledged
        mgr.update_status(oid, make_order_status("Acknowledged"))
        assert mgr.get_order_status(oid).kind == "Acknowledged"

        # 3) 处理 fill
        mgr.add_fill(
            order_id=oid,
            fill_id="f1",
            symbol="BTCUSDT",
            price=50_000.0,
            quantity=0.1,
            fee=0.0,
        )
        status = mgr.get_order_status(oid)
        assert status.kind == "Filled"
        # filled_qty 内部以 Decimal 字符串存
        assert str(status.filled_qty) == "0.1"
        assert status.is_terminal

    def test_cancel_from_acknowledged(self):
        """Acknowledged 状态可被取消;cancel 是终态转换,验证 active 减 1。"""
        mgr = OrderManager()
        mgr.deposit("USDT", 100_000.0)
        oid = mgr.submit(market_order("ETHUSDT", "Buy", 1.0, idempotency_key="k2"))
        mgr.update_status(oid, make_order_status("Acknowledged"))
        mgr.cancel(oid)
        # 取消后 active 计数应减
        assert mgr.active_count() == 0
        # get_order_status 在终态后返回 None(订单从 active 移出)
        assert mgr.get_order_status(oid) is None

    def test_rejected_status(self):
        """Rejected 终态后 active 计数减 1。"""
        mgr = OrderManager()
        mgr.deposit("USDT", 100_000.0)
        oid = mgr.submit(market_order("BTCUSDT", "Buy", 0.1, idempotency_key="k3"))
        mgr.update_status(oid, make_order_status("Rejected", reason="insufficient balance"))
        # 拒绝后 active 计数减 1,get_order_status 找不到(已从 active 移出)
        assert mgr.active_count() == 0
        assert mgr.get_order_status(oid) is None

    def test_history_count_grows(self):
        """submit 后 history_count 至少为 1(订单进入 history)。"""
        mgr = OrderManager()
        mgr.deposit("USDT", 100_000.0)
        oid = mgr.submit(limit_order("BTCUSDT", "Buy", 0.1, 50_000.0, idempotency_key="k4"))
        mgr.update_status(oid, make_order_status("Acknowledged"))
        # submit 之后订单就进入 history, history_count >= 1
        assert mgr.history_count() >= 1
        # add_fill 完成后订单仍应在 history 中
        mgr.add_fill(
            order_id=oid,
            fill_id="f4",
            symbol="BTCUSDT",
            price=50_000.0,
            quantity=0.1,
            fee=0.0,
        )
        assert mgr.history_count() >= 1

    def test_batch_submit(self):
        mgr = OrderManager()
        orders = [market_order("BTCUSDT", "Buy", 0.1, idempotency_key=f"kb{i}") for i in range(3)]
        oids = mgr.batch_submit(orders)
        assert len(oids) == 3
        assert mgr.active_count() == 3


# =============================================================================
# 4. Portfolio
# =============================================================================


class TestPortfolio:
    def test_default_portfolio_is_empty(self):
        p = Portfolio()
        assert p.is_empty()
        assert p.position_count() == 0
        d = p.to_dict()
        assert isinstance(d, dict)

    def test_deposit_updates_balance(self):
        """deposit 后 cash 应有 USDT 余额(以字符串形式存放)。"""
        mgr = OrderManager()
        mgr.deposit("USDT", 10_000.0)
        snap = mgr.snapshot_balance()
        # snap 是 dict,结构参见 oms.py docstring;cash 字段值是 Decimal 字符串
        assert isinstance(snap, dict)
        assert float(snap["cash"].get("USDT", 0)) > 0


# =============================================================================
# 5. 错误映射
# =============================================================================


class TestErrorMapping:
    def test_oms_error_maps_to_409(self):
        """OmsError 应映射为 409(冲突),而非默认 500。"""
        from axon_bridge._errors import AxonQuantError, map_error

        try:
            msg = "synthetic oms failure"
            raise OmsError(msg)
        except OmsError as e:
            mapped = map_error(e)
            assert isinstance(mapped, AxonQuantError)
            assert mapped.http_status == 409
            assert mapped.code == "oms_conflict"
