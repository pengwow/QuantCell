# -*- coding: utf-8 -*-
"""
统一数据类型定义

提供与交易框架无关的数据类型定义，用于策略开发。
这些类型可以在回测和实盘环境中通用。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-02
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """订单类型"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(Enum):
    """订单有效期"""
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill
    DAY = "DAY"  # Day Order


class PositionSide(Enum):
    """持仓方向"""
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass(frozen=True)
class InstrumentId:
    """
    品种标识

    Attributes
    ----------
    symbol : str
        交易品种代码，例如 "BTCUSDT"
    venue : str
        交易所代码，例如 "BINANCE"
    """
    symbol: str
    venue: str

    def __str__(self) -> str:
        return f"{self.symbol}.{self.venue}"

    def __hash__(self) -> int:
        """使 InstrumentId 可哈希，可用作字典 key"""
        return hash((self.symbol, self.venue))

    @classmethod
    def from_string(cls, value: str) -> "InstrumentId":
        """从字符串解析品种标识"""
        parts = value.split(".")
        if len(parts) == 2:
            return cls(symbol=parts[0], venue=parts[1])
        return cls(symbol=value, venue="")


@dataclass
class Bar:
    """
    K线数据
    
    标准化的K线数据结构，与具体交易框架无关。
    
    Attributes
    ----------
    instrument_id : InstrumentId
        品种标识
    bar_type : str
        K线类型，例如 "1-HOUR", "1-MINUTE"
    open : float
        开盘价
    high : float
        最高价
    low : float
        最低价
    close : float
        收盘价
    volume : float
        成交量
    timestamp : datetime
        K线时间戳
    ts_event : int, optional
        事件时间戳（纳秒）
    """
    instrument_id: InstrumentId
    bar_type: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    ts_event: Optional[int] = None
    
    @property
    def symbol(self) -> str:
        """获取品种代码"""
        return self.instrument_id.symbol
    
    @property
    def venue(self) -> str:
        """获取交易所代码"""
        return self.instrument_id.venue


@dataclass
class QuoteTick:
    """
    报价数据
    
    Attributes
    ----------
    instrument_id : InstrumentId
        品种标识
    bid_price : float
        买价
    bid_size : float
        买量
    ask_price : float
        卖价
    ask_size : float
        卖量
    timestamp : datetime
        时间戳
    """
    instrument_id: InstrumentId
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    timestamp: datetime


@dataclass
class TradeTick:
    """
    成交数据
    
    Attributes
    ----------
    instrument_id : InstrumentId
        品种标识
    price : float
        成交价格
    size : float
        成交数量
    aggressor_side : OrderSide
        主动成交方向
    timestamp : datetime
        时间戳
    """
    instrument_id: InstrumentId
    price: float
    size: float
    aggressor_side: OrderSide
    timestamp: datetime


@dataclass
class Order:
    """
    订单数据
    
    Attributes
    ----------
    instrument_id : InstrumentId
        品种标识
    side : OrderSide
        订单方向
    order_type : OrderType
        订单类型
    quantity : Decimal
        订单数量
    price : Optional[Decimal]
        订单价格（市价单为 None）
    time_in_force : TimeInForce
        订单有效期
    order_id : Optional[str]
        订单ID
    timestamp : Optional[datetime]
        创建时间
    """
    instrument_id: InstrumentId
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    order_id: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class Position:
    """
    持仓数据
    
    Attributes
    ----------
    instrument_id : InstrumentId
        品种标识
    side : PositionSide
        持仓方向
    quantity : Decimal
        持仓数量
    avg_price : float
        平均持仓价格
    unrealized_pnl : float
        未实现盈亏
    realized_pnl : float
        已实现盈亏
    timestamp : datetime
        更新时间
    """
    instrument_id: InstrumentId
    side: PositionSide
    quantity: Decimal
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    timestamp: Optional[datetime] = None
    
    @property
    def is_long(self) -> bool:
        """是否为多头持仓"""
        return self.side == PositionSide.LONG
    
    @property
    def is_short(self) -> bool:
        """是否为空头持仓"""
        return self.side == PositionSide.SHORT
    
    @property
    def is_flat(self) -> bool:
        """是否空仓"""
        return self.side == PositionSide.FLAT or self.quantity == 0


@dataclass
class AccountBalance:
    """
    账户余额
    
    Attributes
    ----------
    currency : str
        货币代码
    total : Decimal
        总余额
    free : Decimal
        可用余额
    locked : Decimal
        冻结余额
    """
    currency: str
    total: Decimal
    free: Decimal
    locked: Decimal


# 类型别名，用于兼容不同场景
BarType = str  # 例如 "1-HOUR", "1-MINUTE"
Price = float
Quantity = Decimal
