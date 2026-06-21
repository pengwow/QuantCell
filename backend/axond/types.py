# -*- coding: utf-8 -*-
"""QuantCell 统一类型定义 — 不依赖任何外部量化框架"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"


class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    STOP_LOSS = "StopLoss"
    STOP_LIMIT = "StopLimit"


class TimeInForce(Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class PositionSide(Enum):
    LONG = "Long"
    SHORT = "Short"
    FLAT = "Flat"


@dataclass(frozen=True)
class InstrumentId:
    symbol: str
    venue: str

    def __str__(self) -> str:
        return f"{self.symbol}.{self.venue}"


@dataclass
class Bar:
    instrument_id: InstrumentId
    bar_type: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    ts_event: int


@dataclass
class QuoteTick:
    instrument_id: InstrumentId
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    timestamp: datetime
    ts_event: int


@dataclass
class TradeTick:
    instrument_id: InstrumentId
    price: float
    quantity: float
    aggressor_side: OrderSide
    trade_id: str
    timestamp: datetime
    ts_event: int


@dataclass
class Position:
    instrument_id: InstrumentId
    side: PositionSide
    quantity: Decimal
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class AccountBalance:
    currency: str
    total: Decimal
    available: Decimal
    locked: Decimal = Decimal("0")
