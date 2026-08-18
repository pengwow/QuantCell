"""
测试 LiveTradeRecorder 类

测试内容：
1. 订单事件处理 (OrderAccepted, OrderCanceled, OrderRejected)
2. 成交事件处理 (OrderFilled)
3. 持仓事件处理 (PositionChanged)
4. 事件订阅/取消订阅功能
5. 数据库操作的正确性
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from worker.event_handler import LiveTradeRecorder
from worker.models import WorkerOrder, WorkerPosition, WorkerTrade


# 自定义类模拟真实的 Trader 对象（不是 Mock）
class FakeTrader:
    """模拟真实的 axon_quant Trader 对象（不是 Mock）"""

    pass


class FakeNode:
    """模拟真实的 axon_quant TradingNode 对象（不是 Mock）"""

    pass


class Mockaxon_quantOrderAccepted:
    """模拟 axon_quant 的 OrderAccepted 事件"""

    def __init__(self):
        self.client_order_id = "test-order-123"
        self.venue_order_id = "venue-123"
        self.instrument_id = "BTCUSDT"
        self.order_side = "BUY"
        self.order_type = "MARKET"
        self.order_qty = 0.01
        self.order_px = 50000.0
        self.strategy_id = "strategy-1"
        self.timestamp = datetime.now()


class Mockaxon_quantOrderCanceled:
    """模拟 axon_quant 的 OrderCanceled 事件"""

    def __init__(self):
        self.client_order_id = "test-order-123"
        self.venue_order_id = "venue-123"
        self.instrument_id = "BTCUSDT"
        self.order_side = "BUY"
        self.timestamp = datetime.now()


class Mockaxon_quantOrderRejected:
    """模拟 axon_quant 的 OrderRejected 事件"""

    def __init__(self):
        self.client_order_id = "test-order-123"
        self.reason = "Insufficient balance"
        self.instrument_id = "BTCUSDT"
        self.timestamp = datetime.now()


class Mockaxon_quantOrderFilled:
    """模拟 axon_quant 的 OrderFilled 事件"""

    def __init__(self):
        self.trade_id = "trade-456"
        self.client_order_id = "test-order-123"
        self.venue_order_id = "venue-123"
        self.instrument_id = "BTCUSDT"
        self.order_side = "BUY"
        self.order_type = "MARKET"
        self.last_qty = 0.01
        self.last_px = 50000.0
        self.strategy_id = "strategy-1"
        self.ts_event = (datetime.now() - timedelta(hours=1)).timestamp() * 1e9
        self.commission = Mock()
        self.commission.as_double = Mock(return_value=1.0)
        self.commission.currency = "USDT"
        self.liquidity_side = "TAKER"


class Mockaxon_quantPositionChanged:
    """模拟 axon_quant 的 PositionChanged 事件"""

    def __init__(self):
        self.position_id = "pos-789"
        self.instrument_id = "BTCUSDT"
        self.position_side = "LONG"
        self.qty = 0.01
        self.entry_avg_px = 50000.0
        self.unrealized_pnl = 100.0
        self.realized_pnl = 0.0
        self.is_close = False
        self.timestamp = datetime.now()


class TestLiveTradeRecorder:
    """测试 LiveTradeRecorder 类"""

    @pytest.fixture
    def recorder(self):
        """创建 LiveTradeRecorder 实例"""
        return LiveTradeRecorder(worker_id=1)

    @pytest.fixture
    def mock_trader(self):
        """创建模拟的 trader 对象（模拟真实的 axon_quant 对象结构）"""
        # 使用 FakeTrader 而非 Mock，模拟真实的 Trader 对象
        fake_trader = FakeTrader()
        # msgbus 实际在 trader.kernel.msgbus
        mock_msgbus = Mock()
        fake_kernel = FakeTrader()
        fake_kernel.msgbus = mock_msgbus
        fake_trader.kernel = fake_kernel
        return fake_trader

    @pytest.fixture
    def mock_node(self):
        """创建模拟的 TradingNode 对象"""
        # 使用 FakeNode 而非 Mock，模拟真实的 Node 对象
        fake_node = FakeNode()
        # TradingNode 有 msgbus 属性（通过 @property 暴露）
        mock_msgbus = Mock()
        fake_node.msgbus = mock_msgbus
        return fake_node

    @pytest.fixture
    def mock_order_accepted_event(self):
        """创建模拟的 OrderAccepted 事件"""
        return Mockaxon_quantOrderAccepted()

    @pytest.fixture
    def mock_order_canceled_event(self):
        """创建模拟的 OrderCanceled 事件"""
        return Mockaxon_quantOrderCanceled()

    @pytest.fixture
    def mock_order_rejected_event(self):
        """创建模拟的 OrderRejected 事件"""
        return Mockaxon_quantOrderRejected()

    @pytest.fixture
    def mock_order_filled_event(self):
        """创建模拟的 OrderFilled 事件"""
        return Mockaxon_quantOrderFilled()

    @pytest.fixture
    def mock_position_event(self):
        """创建模拟的 PositionChanged 事件"""
        return Mockaxon_quantPositionChanged()

    @pytest.fixture
    def mock_db_session(self):
        """创建模拟的数据库会话"""
        return Mock()

    def test_subscribe_events(self, recorder, mock_trader, mock_node):
        """测试事件订阅功能（使用 node.msgbus）"""
        recorder.subscribe(mock_trader, node=mock_node)

        # 验证通过 node.msgbus 订阅了正确的事件
        assert mock_node.msgbus.subscribe.call_count == 3
        assert recorder._subscribed is True

    def test_subscribe_events_via_trader_kernel(self, recorder, mock_trader):
        """测试通过 trader.kernel.msgbus 订阅（兼容性测试）"""
        recorder.subscribe(mock_trader)

        # 验证通过 trader.kernel.msgbus 订阅
        assert mock_trader.kernel.msgbus.subscribe.call_count == 3
        assert recorder._subscribed is True

    def test_subscribe_events_via_trader_msgbus_compat(self, recorder):
        """测试通过 trader.msgbus 订阅（兼容旧版本）"""
        fake_trader = FakeTrader()
        fake_trader.msgbus = Mock()  # 直接挂在 trader 上（兼容模式）
        recorder.subscribe(fake_trader)

        assert fake_trader.msgbus.subscribe.call_count == 3
        assert recorder._subscribed is True

    def test_unsubscribe_events(self, recorder, mock_trader, mock_node):
        """测试事件取消订阅功能"""
        recorder.subscribe(mock_trader, node=mock_node)
        recorder.unsubscribe()

        # 验证取消了订阅
        assert mock_node.msgbus.unsubscribe.call_count == 3
        assert recorder._subscribed is False

    def test_handle_order_accepted_with_real_db(self, recorder, mock_order_accepted_event, db_session):
        """测试处理 OrderAccepted 事件 (使用真实的数据库会话)"""

        # 模拟 _get_db 方法
        recorder._get_db = Mock(return_value=db_session)

        # 直接调用 _handle_order_accepted
        recorder._handle_order_accepted(db_session, mock_order_accepted_event)

        # 查询数据库，验证订单被创建
        order = db_session.query(WorkerOrder).filter(WorkerOrder.client_order_id == "test-order-123").first()

        # 验证基本属性
        assert order is not None
        assert order.worker_id == 1
        assert order.symbol == "BTCUSDT"
        assert order.side == "BUY"
        assert order.order_type == "MARKET"
        assert order.quantity == 0.01
        assert order.price == 50000.0
        assert order.status == "ACCEPTED"

    def test_handle_order_canceled_with_real_db(
        self, recorder, mock_order_accepted_event, mock_order_canceled_event, db_session
    ):
        """测试处理 OrderCanceled 事件"""
        from worker.crud import create_order_if_not_exists

        # 首先创建一个已接受的订单
        test_order_data = {
            "worker_id": 1,
            "client_order_id": "test-order-123",
            "venue_order_id": "venue-123",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "price": 50000.0,
            "filled_qty": 0.0,
            "avg_fill_price": 0.0,
            "status": "ACCEPTED",
            "position_id": None,
            "strategy_id": "strategy-1",
        }
        create_order_if_not_exists(db_session, test_order_data)

        # 模拟 _get_db 方法
        recorder._get_db = Mock(return_value=db_session)

        # 直接调用 _handle_order_canceled
        recorder._handle_order_canceled(db_session, mock_order_canceled_event)

        # 查询数据库，验证订单状态更新
        order = db_session.query(WorkerOrder).filter(WorkerOrder.client_order_id == "test-order-123").first()

        assert order is not None
        assert order.status == "CANCELED"

    def test_handle_order_filled_with_real_db(
        self, recorder, mock_order_accepted_event, mock_order_filled_event, db_session
    ):
        """测试处理 OrderFilled 事件"""
        from worker.crud import create_order_if_not_exists

        # 首先创建一个已接受的订单
        test_order_data = {
            "worker_id": 1,
            "client_order_id": "test-order-123",
            "venue_order_id": "venue-123",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "price": 50000.0,
            "filled_qty": 0.0,
            "avg_fill_price": 0.0,
            "status": "ACCEPTED",
            "position_id": None,
            "strategy_id": "strategy-1",
        }
        create_order_if_not_exists(db_session, test_order_data)

        # 模拟 _get_db 方法
        recorder._get_db = Mock(return_value=db_session)

        # 直接调用 _handle_fill
        recorder._handle_fill(db_session, mock_order_filled_event)

        # 验证交易记录被创建
        trade = db_session.query(WorkerTrade).filter(WorkerTrade.trade_id == "trade-456").first()
        assert trade is not None
        assert trade.worker_id == 1
        assert trade.symbol == "BTCUSDT"
        assert trade.side == "BUY"
        assert trade.order_type == "MARKET"
        assert trade.quantity == 0.01
        assert trade.price == 50000.0
        assert trade.amount == 500.0
        assert trade.fee == 1.0
        assert trade.fee_currency == "USDT"

        # 验证订单状态被更新
        order = db_session.query(WorkerOrder).filter(WorkerOrder.client_order_id == "test-order-123").first()
        assert order is not None
        assert order.status == "FILLED"
        assert order.filled_qty == 0.01
        assert order.avg_fill_price == 50000.0

    def test_handle_position_event_with_real_db(self, recorder, mock_position_event, db_session):
        """测试处理 PositionChanged 事件"""
        # 模拟 _get_db 方法
        recorder._get_db = Mock(return_value=db_session)

        # 直接调用 _handle_position
        recorder._handle_position(db_session, mock_position_event)

        # 验证持仓记录被创建
        position = db_session.query(WorkerPosition).filter(WorkerPosition.position_id == "pos-789").first()

        assert position is not None
        assert position.worker_id == 1
        assert position.symbol == "BTCUSDT"
        assert position.side == "LONG"
        assert position.quantity == 0.01
        assert position.entry_price == 50000.0
        assert position.unrealized_pnl == 100.0
        assert position.realized_pnl == 0.0
        assert position.status == "OPEN"

    def test_extract_commission(self, recorder, mock_order_filled_event):
        """测试提取手续费"""
        commission = recorder._extract_commission(mock_order_filled_event)
        assert commission == 1.0

    def test_extract_commission_currency(self, recorder, mock_order_filled_event):
        """测试提取手续费币种"""
        currency = recorder._extract_commission_currency(mock_order_filled_event)
        assert currency == "USDT"

    def test_extract_commission_none(self, recorder):
        """测试提取手续费为 None 的情况"""
        event = Mock()
        event.commission = None
        commission = recorder._extract_commission(event)
        assert commission == 0.0

    def test_extract_commission_currency_none(self, recorder):
        """测试提取手续费币种为 None 的情况"""
        event = Mock()
        event.commission = None
        currency = recorder._extract_commission_currency(event)
        assert currency == "USDT"

    def test_extract_commission_amount_attr(self, recorder):
        """测试提取通过 amount 属性提取手续费"""
        event = Mock()
        commission = Mock()
        commission.amount = 2.5
        event.commission = commission
        extracted = recorder._extract_commission(event)
        assert extracted == 2.5

    def test_extract_commission_float(self, recorder):
        """测试直接提取 float 类型手续费"""
        event = Mock()
        event.commission = 3.0
        extracted = recorder._extract_commission(event)
        assert extracted == 3.0

    def test_extract_commission_invalid_type(self, recorder):
        """测试提取无效类型手续费"""
        event = Mock()
        event.commission = "invalid"
        extracted = recorder._extract_commission(event)
        assert extracted == 0.0

    def test_on_order_event_dispatch(self, recorder, db_session):
        """测试订单事件分发逻辑"""
        recorder._get_db = Mock(return_value=db_session)

        # 模拟各个订单事件
        with patch.object(recorder, "_handle_order_accepted") as mock_handle_accepted:
            event = Mockaxon_quantOrderAccepted()
            # 给event添加类型标识以便 _dispatch_order_event 可以识别
            from axon_quant.core.events import OrderAccepted

            event.__class__ = OrderAccepted
            # 使用 type('MockOrderAccepted', (OrderAccepted,), {})
            mock_order_accepted = type(
                "MockOrderAccepted",
                (OrderAccepted,),
                {
                    "client_order_id": "test-123",
                    "venue_order_id": "venue-123",
                    "instrument_id": "BTCUSDT",
                    "order_side": "BUY",
                    "order_type": "MARKET",
                    "order_qty": 0.01,
                    "order_px": 50000.0,
                    "strategy_id": "strategy-1",
                },
            )()

            recorder._dispatch_order_event(db_session, mock_order_accepted)
            assert mock_handle_accepted.called
