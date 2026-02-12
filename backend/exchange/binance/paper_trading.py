"""
Binance模拟盘交易账户

提供模拟交易功能，包括：
- 模拟账户管理（初始资金、余额追踪）
- 模拟订单簿管理
- 市价/限价订单执行
- 订单状态模拟
- 盈亏计算
- 持仓管理
"""

import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from loguru import logger

from .config import OrderSide, OrderType, OrderStatus, TimeInForce
from .exceptions import BinanceOrderError


@dataclass
class PaperPosition:
    """模拟持仓"""
    symbol: str
    quantity: float
    avg_price: float
    side: str  # "LONG" or "SHORT"
    unrealized_pnl: float = 0.0
    
    def update_unrealized_pnl(self, current_price: float):
        """更新未实现盈亏"""
        if self.side == "LONG":
            self.unrealized_pnl = (current_price - self.avg_price) * self.quantity
        else:
            self.unrealized_pnl = (self.avg_price - current_price) * self.quantity


@dataclass
class PaperOrder:
    """模拟订单"""
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float]
    time_in_force: TimeInForce
    status: OrderStatus
    filled_qty: float = 0.0
    avg_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    @property
    def remaining_qty(self) -> float:
        """剩余未成交数量"""
        return self.quantity - self.filled_qty
    
    @property
    def is_filled(self) -> bool:
        """是否完全成交"""
        return self.status == OrderStatus.FILLED


class PaperTradingAccount:
    """
    Binance模拟盘交易账户
    
    功能：
    - 管理模拟资金余额
    - 执行模拟订单（市价/限价）
    - 追踪持仓和盈亏
    - 模拟订单成交
    """
    
    def __init__(
        self,
        initial_balance: Optional[Dict[str, float]] = None,
        maker_fee: float = 0.001,
        taker_fee: float = 0.001,
    ):
        """
        初始化模拟交易账户
        
        Args:
            initial_balance: 初始资金，如 {"USDT": 10000.0, "BTC": 0.5}
            maker_fee: Maker手续费率
            taker_fee: Taker手续费率
        """
        self.balances: Dict[str, float] = initial_balance if initial_balance is not None else {"USDT": 10000.0}
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        
        # 订单和持仓
        self.orders: Dict[str, PaperOrder] = {}
        self.positions: Dict[str, PaperPosition] = {}
        
        # 成交历史
        self.trades: List[Dict[str, Any]] = []
        
        # 当前市场价格
        self.market_prices: Dict[str, float] = {}
        
        logger.info(f"PaperTradingAccount initialized with balance: {self.balances}")
    
    def update_market_price(self, symbol: str, price: float):
        """更新市场价格"""
        self.market_prices[symbol.upper()] = price
        
        # 更新持仓未实现盈亏
        for position in self.positions.values():
            if position.symbol == symbol.upper():
                position.update_unrealized_pnl(price)
    
    def get_balance(self, asset: str) -> float:
        """获取资产余额"""
        return self.balances.get(asset.upper(), 0.0)
    
    def get_total_balance(self, asset: str) -> float:
        """获取总资产（可用 + 锁定）"""
        # 在模拟盘中，所有余额都是可用的
        return self.get_balance(asset)
    
    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> PaperOrder:
        """
        创建订单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            quantity: 数量
            price: 价格（市价单可为None）
            time_in_force: 有效时间
            
        Returns:
            PaperOrder: 创建的订单
        """
        # 参数验证
        if not symbol or not isinstance(symbol, str):
            raise BinanceOrderError("Invalid symbol", symbol=symbol)
        
        symbol = symbol.upper()
        
        # 验证数量
        if quantity <= 0:
            raise BinanceOrderError("Quantity must be positive", symbol=symbol)
        
        # 验证价格
        if price is not None and price <= 0:
            raise BinanceOrderError("Price must be positive", symbol=symbol)
        
        # 验证订单类型
        if order_type == OrderType.LIMIT and price is None:
            raise BinanceOrderError("Limit order requires price", symbol=symbol)
        
        # 检查余额
        if side == OrderSide.BUY:
            quote_asset = self._get_quote_asset(symbol)
            required_balance = (price or self.market_prices.get(symbol, 0)) * quantity
            if self.get_balance(quote_asset) < required_balance:
                raise BinanceOrderError(
                    f"Insufficient balance: {quote_asset}",
                    symbol=symbol
                )
        else:  # SELL
            base_asset = self._get_base_asset(symbol)
            if self.get_balance(base_asset) < quantity:
                raise BinanceOrderError(
                    f"Insufficient balance: {base_asset}",
                    symbol=symbol
                )
        
        # 创建订单
        order = PaperOrder(
            order_id=str(uuid.uuid4()),
            client_order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            status=OrderStatus.NEW,
        )
        
        self.orders[order.order_id] = order
        
        # 模拟订单成交
        self._process_order(order)
        
        logger.info(f"Created {order_type.value} {side.value} order: {symbol} {quantity} @ {price}")
        return order
    
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 是否成功取消
        """
        if order_id not in self.orders:
            return False
        
        order = self.orders[order_id]
        
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED]:
            return False
        
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now()
        
        logger.info(f"Canceled order: {order_id}")
        return True
    
    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        """获取订单信息"""
        return self.orders.get(order_id)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[PaperOrder]:
        """获取未成交订单"""
        orders = [
            order for order in self.orders.values()
            if order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]
        ]
        
        if symbol:
            orders = [o for o in orders if o.symbol == symbol.upper()]
        
        return orders
    
    def get_position(self, symbol: str) -> Optional[PaperPosition]:
        """获取持仓"""
        return self.positions.get(symbol.upper())
    
    def get_all_positions(self) -> List[PaperPosition]:
        """获取所有持仓"""
        return list(self.positions.values())
    
    def get_account_summary(self) -> Dict[str, Any]:
        """获取账户摘要"""
        total_balance = sum(self.balances.values())
        
        # 计算持仓价值
        position_value = 0.0
        unrealized_pnl = 0.0
        
        for position in self.positions.values():
            current_price = self.market_prices.get(position.symbol, position.avg_price)
            position_value += position.quantity * current_price
            unrealized_pnl += position.unrealized_pnl
        
        return {
            "balances": self.balances.copy(),
            "total_balance": total_balance,
            "position_value": position_value,
            "unrealized_pnl": unrealized_pnl,
            "total_equity": total_balance + position_value + unrealized_pnl,
            "position_count": len(self.positions),
            "open_order_count": len(self.get_open_orders()),
        }
    
    def _process_order(self, order: PaperOrder):
        """处理订单成交"""
        symbol = order.symbol
        current_price = self.market_prices.get(symbol)
        
        if not current_price:
            logger.warning(f"No market price for {symbol}, order pending")
            return
        
        if order.order_type == OrderType.MARKET:
            # 市价单立即成交
            self._execute_order(order, current_price, order.quantity)
            
        elif order.order_type == OrderType.LIMIT and order.price is not None:
            # 限价单检查价格
            if order.side == OrderSide.BUY and order.price >= current_price:
                # 买入限价单：限价 >= 市价，可以成交
                self._execute_order(order, order.price, order.quantity)
            elif order.side == OrderSide.SELL and order.price <= current_price:
                # 卖出限价单：限价 <= 市价，可以成交
                self._execute_order(order, order.price, order.quantity)
    
    def _execute_order(self, order: PaperOrder, price: float, quantity: float):
        """执行订单"""
        symbol = order.symbol
        
        # 计算手续费
        fee_rate = self.taker_fee if order.order_type == OrderType.MARKET else self.maker_fee
        fee = quantity * price * fee_rate
        
        # 更新订单状态
        order.filled_qty = quantity
        order.avg_price = price
        order.status = OrderStatus.FILLED
        order.updated_at = datetime.now()
        
        # 更新余额
        base_asset = self._get_base_asset(symbol)
        quote_asset = self._get_quote_asset(symbol)
        
        if order.side == OrderSide.BUY:
            # 买入：减少quote，增加base
            cost = quantity * price + fee
            self.balances[quote_asset] = self.balances.get(quote_asset, 0) - cost
            self.balances[base_asset] = self.balances.get(base_asset, 0) + quantity
        else:
            # 卖出：减少base，增加quote
            revenue = quantity * price - fee
            self.balances[base_asset] = self.balances.get(base_asset, 0) - quantity
            self.balances[quote_asset] = self.balances.get(quote_asset, 0) + revenue
        
        # 更新持仓
        self._update_position(symbol, order.side, quantity, price)
        
        # 记录成交
        self.trades.append({
            "trade_id": str(uuid.uuid4()),
            "order_id": order.order_id,
            "symbol": symbol,
            "side": order.side.value,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "time": datetime.now(),
        })
        
        logger.info(f"Executed {order.side.value} order: {symbol} {quantity} @ {price}")
    
    def _update_position(self, symbol: str, side: OrderSide, quantity: float, price: float):
        """更新持仓"""
        symbol = symbol.upper()
        position = self.positions.get(symbol)
        
        if side == OrderSide.BUY:
            if position and position.side == "LONG":
                # 增加多头持仓
                total_qty = position.quantity + quantity
                position.avg_price = (position.quantity * position.avg_price + quantity * price) / total_qty
                position.quantity = total_qty
            elif position and position.side == "SHORT":
                # 减少空头持仓
                if quantity >= position.quantity:
                    # 平仓并开多
                    remaining = quantity - position.quantity
                    if remaining > 0:
                        self.positions[symbol] = PaperPosition(
                            symbol=symbol,
                            quantity=remaining,
                            avg_price=price,
                            side="LONG"
                        )
                    else:
                        del self.positions[symbol]
                else:
                    position.quantity -= quantity
            else:
                # 新开多头持仓
                self.positions[symbol] = PaperPosition(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=price,
                    side="LONG"
                )
        else:  # SELL
            if position and position.side == "SHORT":
                # 增加空头持仓
                total_qty = position.quantity + quantity
                position.avg_price = (position.quantity * position.avg_price + quantity * price) / total_qty
                position.quantity = total_qty
            elif position and position.side == "LONG":
                # 减少多头持仓
                if quantity >= position.quantity:
                    # 平仓并开空
                    remaining = quantity - position.quantity
                    if remaining > 0:
                        self.positions[symbol] = PaperPosition(
                            symbol=symbol,
                            quantity=remaining,
                            avg_price=price,
                            side="SHORT"
                        )
                    else:
                        del self.positions[symbol]
                else:
                    position.quantity -= quantity
            else:
                # 新开空头持仓
                self.positions[symbol] = PaperPosition(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=price,
                    side="SHORT"
                )
    
    def _get_base_asset(self, symbol: str) -> str:
        """获取基础资产"""
        # 简单处理：假设交易对格式为 BASEQUOTE
        symbol = symbol.upper()
        if "USDT" in symbol:
            return symbol.replace("USDT", "")
        elif "BTC" in symbol:
            return symbol.replace("BTC", "")
        elif "ETH" in symbol:
            return symbol.replace("ETH", "")
        return symbol[:3]  # 默认取前3个字符
    
    def _get_quote_asset(self, symbol: str) -> str:
        """获取计价资产"""
        symbol = symbol.upper()
        if "USDT" in symbol:
            return "USDT"
        elif "BTC" in symbol:
            return "BTC"
        elif "ETH" in symbol:
            return "ETH"
        return symbol[3:]  # 默认取后3个字符
