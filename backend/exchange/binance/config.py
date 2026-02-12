"""
Binance模块配置和数据模型
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class TradingMode(str, Enum):
    """交易模式"""
    SPOT = "spot"
    FUTURES = "futures"
    MARGIN = "margin"


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """订单状态"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PENDING_CANCEL = "PENDING_CANCEL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(str, Enum):
    """有效时间"""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


@dataclass
class BinanceConfig:
    """Binance配置"""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet: bool = True  # 默认使用测试网
    trading_mode: TradingMode = TradingMode.SPOT
    tld: str = "com"  # 顶级域名，com/us等
    
    # WebSocket配置
    websocket_enabled: bool = True
    websocket_auto_reconnect: bool = True
    websocket_reconnect_interval: int = 5  # 秒
    websocket_ping_interval: int = 30  # 秒
    
    # 请求配置
    request_timeout: int = 30  # 秒
    max_retries: int = 3
    retry_delay: float = 1.0  # 秒
    
    # 代理配置
    proxy_url: Optional[str] = None
    
    # 日志配置
    verbose: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "api_key": self.api_key,
            "api_secret": self.api_secret,
            "testnet": self.testnet,
            "trading_mode": self.trading_mode.value,
            "tld": self.tld,
            "websocket_enabled": self.websocket_enabled,
            "websocket_auto_reconnect": self.websocket_auto_reconnect,
            "websocket_reconnect_interval": self.websocket_reconnect_interval,
            "request_timeout": self.request_timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "proxy_url": self.proxy_url,
            "verbose": self.verbose,
        }


@dataclass
class OrderRequest:
    """订单请求"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    time_in_force: Optional[TimeInForce] = None
    stop_price: Optional[float] = None
    iceberg_qty: Optional[float] = None
    new_client_order_id: Optional[str] = None
    
    def to_binance_params(self) -> Dict[str, Any]:
        """转换为Binance API参数"""
        params = {
            "symbol": self.symbol.upper(),
            "side": self.side.value,
            "type": self.order_type.value,
            "quantity": self.quantity,
        }
        
        if self.price is not None:
            params["price"] = self.price
        
        if self.time_in_force is not None:
            params["timeInForce"] = self.time_in_force.value
        
        if self.stop_price is not None:
            params["stopPrice"] = self.stop_price
        
        if self.iceberg_qty is not None:
            params["icebergQty"] = self.iceberg_qty
        
        if self.new_client_order_id is not None:
            params["newClientOrderId"] = self.new_client_order_id
        
        return params


@dataclass
class OrderResponse:
    """订单响应"""
    symbol: str
    order_id: int
    client_order_id: str
    transact_time: int
    price: str
    orig_qty: str
    executed_qty: str
    status: OrderStatus
    time_in_force: TimeInForce
    order_type: OrderType
    side: OrderSide
    
    @classmethod
    def from_binance_response(cls, data: Dict[str, Any]) -> "OrderResponse":
        """从Binance响应创建"""
        return cls(
            symbol=data["symbol"],
            order_id=data["orderId"],
            client_order_id=data["clientOrderId"],
            transact_time=data["transactTime"],
            price=data["price"],
            orig_qty=data["origQty"],
            executed_qty=data["executedQty"],
            status=OrderStatus(data["status"]),
            time_in_force=TimeInForce(data["timeInForce"]),
            order_type=OrderType(data["type"]),
            side=OrderSide(data["side"]),
        )


@dataclass
class AccountBalance:
    """账户余额"""
    asset: str
    free: float
    locked: float
    
    @property
    def total(self) -> float:
        """总资产"""
        return self.free + self.locked


@dataclass
class TickerData:
    """行情数据"""
    symbol: str
    price: float
    timestamp: int
