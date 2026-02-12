"""
交易所类型定义模块

提供交易所相关的类型定义，使用TypedDict和dataclass确保类型安全。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_LIMIT = "stop_loss_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"
    LIMIT_MAKER = "limit_maker"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    PENDING_CANCEL = "pending_cancel"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXPIRED_IN_MATCH = "expired_in_match"


class TimeInForce(Enum):
    """订单有效期"""
    GTC = "GTC"  # Good Till Canceled
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill
    GTX = "GTX"  # Good Till Crossing


class TradingMode(Enum):
    """交易模式"""
    SPOT = "spot"
    MARGIN = "margin"
    FUTURES = "futures"


class MarginMode(Enum):
    """保证金模式"""
    NONE = "none"
    CROSS = "cross"
    ISOLATED = "isolated"


class KlineInterval(Enum):
    """K线时间间隔"""
    INTERVAL_1M = "1m"
    INTERVAL_3M = "3m"
    INTERVAL_5M = "5m"
    INTERVAL_15M = "15m"
    INTERVAL_30M = "30m"
    INTERVAL_1H = "1h"
    INTERVAL_2H = "2h"
    INTERVAL_4H = "4h"
    INTERVAL_6H = "6h"
    INTERVAL_8H = "8h"
    INTERVAL_12H = "12h"
    INTERVAL_1D = "1d"
    INTERVAL_3D = "3d"
    INTERVAL_1W = "1w"
    INTERVAL_1MO = "1M"


@dataclass
class Ticker:
    """行情数据类"""
    symbol: str
    price: Decimal
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    bid_volume: Optional[Decimal] = None
    ask_volume: Optional[Decimal] = None
    volume_24h: Optional[Decimal] = None
    quote_volume_24h: Optional[Decimal] = None
    change_24h: Optional[Decimal] = None
    change_percent_24h: Optional[Decimal] = None
    high_24h: Optional[Decimal] = None
    low_24h: Optional[Decimal] = None
    timestamp: Optional[int] = None


@dataclass
class OHLCV:
    """K线数据类"""
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: Optional[int] = None
    quote_volume: Optional[Decimal] = None
    trades: Optional[int] = None
    taker_buy_base_volume: Optional[Decimal] = None
    taker_buy_quote_volume: Optional[Decimal] = None


@dataclass
class OrderBookLevel:
    """订单簿档位"""
    price: Decimal
    quantity: Decimal


@dataclass
class OrderBook:
    """订单簿数据类"""
    symbol: str
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    last_update_id: Optional[int] = None
    timestamp: Optional[int] = None


@dataclass
class Balance:
    """余额数据类"""
    asset: str
    free: Decimal
    locked: Decimal
    total: Decimal = field(init=False)

    def __post_init__(self):
        self.total = self.free + self.locked


@dataclass
class Order:
    """订单数据类"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    client_order_id: Optional[str] = None
    time_in_force: Optional[TimeInForce] = None
    stop_price: Optional[Decimal] = None
    iceberg_quantity: Optional[Decimal] = None
    is_working: bool = True
    is_isolated: bool = False


@dataclass
class Trade:
    """成交数据类"""
    trade_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_asset: str
    timestamp: int
    order_id: Optional[str] = None
    is_maker: bool = False
    is_buyer: bool = True


@dataclass
class AccountInfo:
    """账户信息数据类"""
    account_type: str
    can_trade: bool
    can_withdraw: bool
    can_deposit: bool
    update_time: Optional[int] = None
    permissions: List[str] = field(default_factory=list)


@dataclass
class Position:
    """持仓数据类（合约）"""
    symbol: str
    position_side: str  # LONG or SHORT
    position_amount: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_profit: Decimal
    liquidation_price: Optional[Decimal] = None
    leverage: int = 1
    margin_type: str = "cross"
    isolated_margin: Optional[Decimal] = None
    notional_value: Optional[Decimal] = None


@dataclass
class FundingRate:
    """资金费率数据类"""
    symbol: str
    funding_rate: Decimal
    funding_time: int
    mark_price: Optional[Decimal] = None
    index_price: Optional[Decimal] = None
    estimated_settle_price: Optional[Decimal] = None
    last_funding_rate: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None


@dataclass
class StakingProduct:
    """质押产品数据类"""
    product_id: str
    product_name: str
    asset: str
    duration: int
    apy: Decimal
    min_purchase_amount: Decimal
    max_purchase_amount: Decimal
    status: str
    can_purchase: bool
    can_redeem: bool


@dataclass
class SubAccount:
    """子账户数据类"""
    email: str
    sub_account_id: str
    status: str
    is_freeze: bool
    create_time: int
    is_managed_sub_account: bool = False
    is_asset_management_sub_account: bool = False


class ExchangeFeatures(TypedDict, total=False):
    """交易所功能特性字典"""
    # 基础功能
    spot_trading: bool
    margin_trading: bool
    futures_trading: bool
    
    # 订单功能
    stoploss_on_exchange: bool
    stoploss_order_types: Dict[str, str]
    stoploss_blocks_assets: bool
    order_time_in_force: List[str]
    
    # 市场数据
    ohlcv_candle_limit: int
    ohlcv_has_history: bool
    ohlcv_partial_candle: bool
    tickers_have_bid_ask: bool
    tickers_have_price: bool
    tickers_have_quote_volume: bool
    tickers_have_percentage: bool
    
    # 交易功能
    fetch_my_trades: bool
    fetch_trades: bool
    trades_pagination: str
    trades_pagination_arg: str
    trades_has_history: bool
    
    # 订单簿
    l2_limit_range: Optional[List[int]]
    l2_limit_range_required: bool
    
    # 高级功能
    sub_account: bool
    staking: bool
    savings: bool
    convert: bool
    margin_loan: bool
    futures_leverage: bool
    funding_rate: bool
    
    # WebSocket
    ws_enabled: bool


# 类型别名
Tickers = Dict[str, Ticker]
Balances = Dict[str, Balance]
OHLCVList = List[OHLCV]
OrderList = List[Order]
TradeList = List[Trade]
PositionList = List[Position]
