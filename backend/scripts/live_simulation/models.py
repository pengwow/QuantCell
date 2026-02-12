"""
数据模型定义

定义模拟测试系统中使用的所有数据模型，与QuantCell框架保持一致。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class DataType(str, Enum):
    """数据类型枚举"""
    KLINE = "kline"
    TICK = "tick"
    DEPTH = "depth"
    TRADE = "trade"


class SignalType(str, Enum):
    """信号类型枚举"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


class OrderSide(str, Enum):
    """订单方向枚举"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """订单类型枚举"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """订单状态枚举"""
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class WorkerState(str, Enum):
    """Worker状态枚举"""
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class SimulationState(str, Enum):
    """模拟测试状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class KlineData:
    """K线数据模型"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str = "1m"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "interval": self.interval,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KlineData":
        return cls(
            symbol=data["symbol"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data["volume"]),
            interval=data.get("interval", "1m"),
        )


@dataclass
class TickData:
    """Tick数据模型"""
    symbol: str
    timestamp: datetime
    price: float
    volume: float
    side: str  # buy/sell
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "volume": self.volume,
            "side": self.side,
        }


@dataclass
class MarketDataMessage:
    """市场数据消息模型"""
    symbol: str
    data_type: DataType
    timestamp: datetime
    data: Dict[str, Any]
    source: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "data_type": self.data_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "source": self.source,
        }
    
    @classmethod
    def from_kline(cls, kline: KlineData, source: Optional[str] = None) -> "MarketDataMessage":
        return cls(
            symbol=kline.symbol,
            data_type=DataType.KLINE,
            timestamp=kline.timestamp,
            data=kline.to_dict(),
            source=source,
        )


@dataclass
class TradeSignal:
    """交易信号模型"""
    symbol: str
    signal_type: SignalType
    strength: float  # -1.0 to 1.0
    timestamp: datetime
    price: float
    volume: float
    strategy_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not -1.0 <= self.strength <= 1.0:
            raise ValueError("Signal strength must be between -1.0 and 1.0")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "strength": self.strength,
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "volume": self.volume,
            "strategy_id": self.strategy_id,
            "params": self.params,
        }


@dataclass
class OrderInfo:
    """订单信息模型"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: float = 0.0
    avg_price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if not self.order_id:
            self.order_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "status": self.status.value,
            "filled_qty": self.filled_qty,
            "avg_price": self.avg_price,
            "timestamp": self.timestamp.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class PositionInfo:
    """持仓信息模型"""
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        # 初始化时计算未实现盈亏
        self.unrealized_pnl = (self.current_price - self.avg_price) * self.quantity
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_price": self.avg_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def update_price(self, new_price: float):
        """更新当前价格并计算未实现盈亏"""
        self.current_price = new_price
        self.unrealized_pnl = (new_price - self.avg_price) * self.quantity


@dataclass
class WorkerStatus:
    """Worker状态模型"""
    worker_id: str
    state: WorkerState = WorkerState.INITIALIZING
    strategy_name: Optional[str] = None
    symbols: List[str] = field(default_factory=list)
    messages_processed: int = 0
    orders_placed: int = 0
    errors_count: int = 0
    last_error: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "state": self.state.value,
            "strategy_name": self.strategy_name,
            "symbols": self.symbols,
            "messages_processed": self.messages_processed,
            "orders_placed": self.orders_placed,
            "errors_count": self.errors_count,
            "last_error": self.last_error,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "metadata": self.metadata,
        }
    
    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.now()
    
    def update_state(self, new_state: WorkerState):
        """更新Worker状态"""
        self.state = new_state
        self.update_heartbeat()


@dataclass
class SimulationMetrics:
    """模拟测试指标模型"""
    # 时间指标
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration_ms: float = 0.0
    data_push_duration_ms: float = 0.0
    
    # 数据指标
    total_data_points: int = 0
    data_points_pushed: int = 0
    push_rate: float = 0.0  # 每秒推送数据点数
    
    # 交易指标
    total_signals: int = 0
    total_orders: int = 0
    filled_orders: int = 0
    canceled_orders: int = 0
    total_trades: int = 0
    
    # 盈亏指标
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    
    # 性能指标
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    
    # 异常指标
    exceptions_count: int = 0
    network_errors: int = 0
    data_errors: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration_ms": self.total_duration_ms,
            "data_push_duration_ms": self.data_push_duration_ms,
            "total_data_points": self.total_data_points,
            "data_points_pushed": self.data_points_pushed,
            "push_rate": self.push_rate,
            "total_signals": self.total_signals,
            "total_orders": self.total_orders,
            "filled_orders": self.filled_orders,
            "canceled_orders": self.canceled_orders,
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "avg_latency_ms": self.avg_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "min_latency_ms": self.min_latency_ms,
            "exceptions_count": self.exceptions_count,
            "network_errors": self.network_errors,
            "data_errors": self.data_errors,
        }


@dataclass
class WebSocketMessage:
    """WebSocket消息模型（与QuantCell协议兼容）"""
    type: str
    id: str
    timestamp: float
    data: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "data": self.data,
        }
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class SimulationEvent:
    """模拟事件模型"""
    event_type: str
    timestamp: datetime
    description: str
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "data": self.data,
        }
