# 策略基类
# 支持回测和实盘两种模式

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from loguru import logger


getcontext().prec = 28


class StrategyBase(ABC):
    """
    策略基类
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
        
        # 新增：风险控制属性
        self.stop_loss = params.get('stop_loss', 0.05)
        self.take_profit = params.get('take_profit', 0.1)
        self.max_position_size = params.get('max_position_size', 1.0)
        self.position_adjustment_enabled = params.get('position_adjustment_enabled', False)
        
        # 新增：持仓管理
        self.max_open_positions = params.get('max_open_positions', 5)
        self.current_open_positions = 0
        
        # 新增：订单超时
        self.entry_timeout = params.get('entry_timeout', 300)
        self.exit_timeout = params.get('exit_timeout', 300)
        
        # 新增：保护机制
        self.cooldown_period = params.get('cooldown_period', 3600)
        self.max_drawdown = params.get('max_drawdown', 0.1)
        self.max_drawdown_protection_enabled = params.get('max_drawdown_protection_enabled', False)
        self.stoploss_guard_enabled = params.get('stoploss_guard_enabled', False)
        self.low_profit_protection_enabled = params.get('low_profit_protection_enabled', False)
        self.low_profit_threshold = params.get('low_profit_threshold', 0.05)
        
        # 新增：冷却期管理
        self.cooldowns = {}
        
        # 新增：杠杆支持
        self.leverage_enabled = params.get('leverage_enabled', False)
        self.default_leverage = params.get('default_leverage', 1.0)
        self.max_leverage = params.get('max_leverage', 10.0)
        self.symbol_leverage = {}
        
        # 新增：订单管理器和持仓管理器
        from ..order_manager import OrderManager
        from ..position_manager import PositionManager
        self.order_manager = OrderManager(self)
        self.position_manager = PositionManager(self)
    
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
    
    def on_stop(self, bar: Dict[str, Any]):
        """
        回测结束回调
        
        在回测结束时调用，用于执行强制平仓等清理操作
        
        参数：
        - bar: 最后一根K线数据
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
    
    # 新增：风险控制方法
    def check_stop_loss(self, current_price: float, trade: Dict[str, Any]) -> bool:
        """
        检查止损
        
        参数：
        - current_price: 当前价格
        - trade: 交易数据
        
        返回：
        - bool: 是否触发止损
        """
        if self.stop_loss <= 0:
            return False
        
        if trade['direction'] in ['long', 'buy']:
            pnl = (current_price - trade['entry_price']) * trade['volume']
            if pnl < 0 and abs(pnl) / trade['volume'] >= trade['entry_price'] * self.stop_loss:
                logger.info(f"触发止损: {trade['symbol']}, PnL: {pnl:.2f}")
                return True
        else:
            pnl = (trade['entry_price'] - current_price) * trade['volume']
            if pnl < 0 and abs(pnl) / trade['volume'] >= trade['entry_price'] * self.stop_loss:
                logger.info(f"触发止损: {trade['symbol']}, PnL: {pnl:.2f}")
                return True
        
        return False
    
    def check_take_profit(self, current_price: float, trade: Dict[str, Any]) -> bool:
        """
        检查止盈
        
        参数：
        - current_price: 当前价格
        - trade: 交易数据
        
        返回：
        - bool: 是否触发止盈
        """
        if self.take_profit <= 0:
            return False
        
        if trade['direction'] in ['long', 'buy']:
            pnl = (current_price - trade['entry_price']) * trade['volume']
            if pnl > 0 and pnl / trade['volume'] >= trade['entry_price'] * self.take_profit:
                logger.info(f"触发止盈: {trade['symbol']}, PnL: {pnl:.2f}")
                return True
        else:
            pnl = (trade['entry_price'] - current_price) * trade['volume']
            if pnl > 0 and pnl / trade['volume'] >= trade['entry_price'] * self.take_profit:
                logger.info(f"触发止盈: {trade['symbol']}, PnL: {pnl:.2f}")
                return True
        
        return False
    
    def confirm_trade_entry(self, symbol: str, price: float, volume: float) -> bool:
        """
        确认入场交易
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - bool: 是否允许入场
        """
        # 检查冷却期
        if not self._check_cooldown(symbol):
            return False
        
        # 检查最大持仓数
        if self.current_open_positions >= self.max_open_positions:
            logger.warning(f"已达到最大持仓数: {self.max_open_positions}")
            return False
        
        # 检查最大回撤
        if self.max_drawdown_protection_enabled and not self._check_max_drawdown():
            return False
        
        return True
    
    def confirm_trade_exit(self, symbol: str, price: float, volume: float) -> bool:
        """
        确认出场交易
        
        参数：
        - symbol: 交易对
        - price: 价格
        - volume: 数量
        
        返回：
        - bool: 是否允许出场
        """
        # 检查低利润对保护
        if self.low_profit_protection_enabled:
            trade = self.get_position(symbol)
            if trade:
                pnl = self.calculate_pnl(trade['entry_price'], price, volume, trade['direction'])
                if 0 < pnl / volume < trade['entry_price'] * self.low_profit_threshold:
                    logger.warning(f"低利润对保护: {symbol}, PnL: {pnl:.2f}")
                    return False
        
        return True
    
    def _check_cooldown(self, symbol: str) -> bool:
        """
        检查冷却期（内部方法）
        
        参数：
        - symbol: 交易对
        
        返回：
        - bool: 是否在冷却期中
        """
        if symbol in self.cooldowns:
            cooldown_until = self.cooldowns[symbol]
            if datetime.now() < cooldown_until:
                logger.warning(f"交易对 {symbol} 在冷却期中")
                return False
        
        return True
    
    def _check_max_drawdown(self) -> bool:
        """
        检查最大回撤（内部方法）
        
        返回：
        - bool: 是否超过最大回撤
        """
        # 计算当前回撤
        current_drawdown = self._calculate_current_drawdown()
        
        if current_drawdown > self.max_drawdown:
            logger.warning(f"当前回撤 {current_drawdown:.2%} 超过最大值 {self.max_drawdown:.2%}")
            return False
        
        return True
    
    def _calculate_current_drawdown(self) -> float:
        """
        计算当前回撤（内部方法）
        
        返回：
        - float: 当前回撤比例
        """
        # 实现回撤计算逻辑
        # 这里简化处理，实际应该根据历史数据计算
        return 0.0
    
    def set_cooldown(self, symbol: str, duration: int):
        """
        设置冷却期
        
        参数：
        - symbol: 交易对
        - duration: 冷却时长（秒）
        """
        self.cooldowns[symbol] = datetime.now() + timedelta(seconds=duration)
        logger.info(f"交易对 {symbol} 已设置冷却期 {duration} 秒")
    
    def get_leverage(self, symbol: str) -> float:
        """
        获取杠杆倍数
        
        参数：
        - symbol: 交易对
        
        返回：
        - float: 杠杆倍数
        """
        if not self.leverage_enabled:
            return 1.0
        
        return self.symbol_leverage.get(symbol, self.default_leverage)
    
    def set_leverage(self, symbol: str, leverage: float):
        """
        设置杠杆倍数
        
        参数：
        - symbol: 交易对
        - leverage: 杠杆倍数
        """
        if not self.leverage_enabled:
            logger.warning("杠杆交易未启用")
            return
        
        if leverage < 1.0 or leverage > self.max_leverage:
            logger.warning(f"杠杆倍数 {leverage} 超出范围 [1.0, {self.max_leverage}]")
            return
        
        self.symbol_leverage[symbol] = leverage
        logger.info(f"交易对 {symbol} 杠杆已更新为 {leverage}x")
