# 统一策略基类
# 支持回测和实盘两种模式

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import numpy as np
import pandas as pd
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from loguru import logger


getcontext().prec = 28


class UnifiedStrategyBase(ABC):
    """
    统一策略基类
    支持回测和实盘两种模式
    """
    
    def __init__(self, params: Dict[str, Any]):
        """
        初始化策略
        
        参数：
        - params: 策略参数
        """
        self.params = params
        self.positions = {}
        self.orders = {}
        self.trades = []
        self.indicators = {}
        
        # 加密货币支持
        self.contract_type = params.get('contract_type', 'spot')
        self.price_precision = params.get('price_precision', 8)
        self.size_precision = params.get('size_precision', 3)
        
        # 永续合约特有属性
        if self.contract_type == 'perpetual':
            self.funding_interval = params.get('funding_interval', 8)
            self.funding_rates = []
            self.mark_prices = []
    
    @abstractmethod
    def on_init(self):
        """
        策略初始化回调
        """
        pass
    
    @abstractmethod
    def on_bar(self, bar: Dict[str, Any]):
        """
        K线数据回调
        
        参数：
        - bar: K线数据字典，包含 Open, High, Low, Close, Volume 等
        """
        pass
    
    def on_tick(self, tick: Dict[str, Any]):
        """
        Tick 数据回调（实盘模式）
        
        参数：
        - tick: Tick 数据字典
        """
        pass
    
    def on_order(self, order: Dict[str, Any]):
        """
        订单状态更新回调
        
        参数：
        - order: 订单数据字典
        """
        pass
    
    def on_trade(self, trade: Dict[str, Any]):
        """
        成交回调
        
        参数：
        - trade: 交易数据字典
        """
        pass
    
    def on_funding_rate(self, funding_rate: float, mark_price: float):
        """
        资金费率回调（永续合约）
        
        参数：
        - funding_rate: 资金费率
        - mark_price: 标记价格
        """
        pass
    
    def buy(self, symbol: str, price: float, volume: float) -> str:
        """
        买入
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - str: 订单 ID
        """
        return self._send_order(symbol, 'buy', price, volume)
    
    def sell(self, symbol: str, price: float, volume: float) -> str:
        """
        卖出
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - str: 订单 ID
        """
        return self._send_order(symbol, 'sell', price, volume)
    
    def long(self, symbol: str, price: float, volume: float) -> str:
        """
        开多
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - str: 订单 ID
        """
        return self._send_order(symbol, 'long', price, volume)
    
    def short(self, symbol: str, price: float, volume: float) -> str:
        """
        开空
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - str: 订单 ID
        """
        return self._send_order(symbol, 'short', price, volume)
    
    def cover(self, symbol: str, price: float, volume: float) -> str:
        """
        平多
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - str: 订单 ID
        """
        return self._send_order(symbol, 'cover', price, volume)
    
    def close_short(self, symbol: str, price: float, volume: float) -> str:
        """
        平空
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - str: 订单 ID
        """
        return self._send_order(symbol, 'close_short', price, volume)
    
    def _send_order(self, symbol: str, direction: str, 
                  price: float, volume: float) -> str:
        """
        发送订单（内部方法）
        
        参数：
        - symbol: 交易对
        - direction: 方向
        - price: 价格
        - volume: 数量
        
        返回：
        - str: 订单 ID
        """
        order_id = f"{symbol}_{direction}_{datetime.now().timestamp()}"
        
        order = {
            'order_id': order_id,
            'symbol': symbol,
            'direction': direction,
            'price': self._round_price(price),
            'volume': self._round_size(volume),
            'status': 'pending',
            'timestamp': datetime.now()
        }
        
        self.orders[order_id] = order
        logger.info(f"订单已发送: {order_id}, 方向: {direction}, 价格: {price}, 数量: {volume}")
        
        return order_id
    
    def _round_price(self, price: float) -> float:
        """
        价格四舍五入（高精度）
        
        参数：
        - price: 价格
        
        返回：
        - float: 四舍五入后的价格
        """
        d = Decimal(str(price))
        return float(d.quantize(
            Decimal(f'1e-{self.price_precision}'),
            rounding=ROUND_HALF_UP
        ))
    
    def _round_size(self, size: float) -> float:
        """
        数量向下取整（高精度）
        
        参数：
        - size: 数量
        
        返回：
        - float: 向下取整后的数量
        """
        d = Decimal(str(size))
        return float(d.quantize(
            Decimal(f'1e-{self.size_precision}'),
            rounding=ROUND_DOWN
        ))
    
    def get_position(self, symbol: str) -> Dict[str, Any]:
        """
        获取持仓
        
        参数：
        - symbol: 交易对
        
        返回：
        - dict: 持仓信息
        """
        return self.positions.get(symbol, {})
    
    def get_cash(self) -> float:
        """
        获取可用资金
        
        返回：
        - float: 可用资金
        """
        # 由子类实现
        pass
    
    def get_portfolio_value(self) -> float:
        """
        获取组合价值
        
        返回：
        - float: 组合价值
        """
        cash = self.get_cash()
        positions_value = 0.0
        
        for symbol, position in self.positions.items():
            if 'current_price' in position:
                positions_value += position['quantity'] * position['current_price']
        
        return cash + positions_value
    
    def calculate_pnl(self, entry_price: float, exit_price: float, 
                   size: float, direction: str) -> float:
        """
        计算盈亏
        
        参数：
        - entry_price: 入场价格
        - exit_price: 出场价格
        - size: 数量
        - direction: 方向
        
        返回：
        - float: 盈亏
        """
        if direction in ['long', 'cover']:
            return (exit_price - entry_price) * size
        else:
            return (entry_price - exit_price) * size
    
    def write_log(self, msg: str):
        """
        写入日志
        
        参数：
        - msg: 日志消息
        """
        logger.info(f"[{self.__class__.__name__}] {msg}")
