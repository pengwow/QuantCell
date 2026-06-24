from dataclasses import dataclass
from enum import Enum

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: float
    price: float = 0.0
    order_id: str = ""
