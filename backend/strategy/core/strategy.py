# 策略基类
# 基于 NautilusTrader 框架的策略实现

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
import warnings

from loguru import logger

# NautilusTrader 导入
from nautilus_trader.trading.strategy import Strategy as NTStrategy
from nautilus_trader.config import StrategyConfig as NTStrategyConfig
from nautilus_trader.model.data import Bar as NTBar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.orders import MarketOrder, LimitOrder


getcontext().prec = 28


class StrategyConfig(NTStrategyConfig, frozen=True):
    """
    策略配置类
    
    继承 NautilusTrader StrategyConfig，添加扩展配置项
    """
    # 风险控制配置
    stop_loss: float = 0.05
    take_profit: float = 0.1
    max_position_size: float = 1.0
    
    # 持仓管理配置
    max_open_positions: int = 5
    
    # 订单超时配置（秒）
    entry_timeout: int = 300
    exit_timeout: int = 300
    
    # 保护机制配置
    cooldown_period: int = 3600
    max_drawdown: float = 0.1
    
    # 加密货币配置
    contract_type: str = "spot"  # spot, perpetual
    price_precision: int = 8
    size_precision: int = 3
    
    # 杠杆配置
    leverage_enabled: bool = False
    default_leverage: float = 1.0
    max_leverage: float = 10.0


class Strategy(NTStrategy):
    """
    策略基类
    
    基于 NautilusTrader Strategy 实现，提供策略开发的基础功能。
    支持回测和实盘两种模式，内置风险控制和持仓管理。
    
    使用方式:
        class MyStrategy(Strategy):
            def on_bar(self, bar):
                # 策略逻辑
                if self.should_buy(bar):
                    self.buy(bar)
    """
    
    def __init__(self, config: StrategyConfig):
        """
        初始化策略
        
        Args:
            config: 策略配置对象
        """
        super().__init__(config)
        
        # 策略状态
        self._initialized = False
        self._positions_count = 0
        
        # 交易统计
        self.trades: List[Dict[str, Any]] = []
        self.total_pnl = 0.0
        self.winning_trades = 0
        self.total_trades = 0
        
        # 冷却期管理
        self._cooldowns: Dict[str, datetime] = {}
        
        logger.info(f"策略初始化完成: {self.__class__.__name__}")
    
    def on_start(self):
        """
        策略启动回调
        
        在策略开始运行时调用，用于初始化操作
        """
        self._initialized = True
        logger.info(f"策略启动: {self.__class__.__name__}")
        self.on_init()
    
    def on_init(self):
        """
        策略初始化
        
        子类可以重写此方法进行自定义初始化
        """
        pass
    
    def on_bar(self, bar: NTBar):
        """
        K线数据回调
        
        每当收到新的K线数据时调用。
        
        Args:
            bar: NautilusTrader Bar 对象
        """
        pass
    
    def on_stop(self):
        """
        策略停止回调
        
        在策略停止时调用，用于清理操作
        """
        logger.info(f"策略停止: {self.__class__.__name__}")
        logger.info(f"交易统计: 总交易={self.total_trades}, 盈利={self.winning_trades}")
    
    def buy(self, symbol: str, price: Optional[float] = None, 
            volume: Optional[float] = None) -> str:
        """
        买入
        
        Args:
            symbol: 交易品种标识
            price: 价格（None 表示市价）
            volume: 数量
            
        Returns:
            订单ID
        """
        if volume is None:
            volume = self._config.max_position_size
        
        instrument_id = InstrumentId.from_str(symbol)
        
        if price is None:
            # 市价单
            order = self.order_factory.market(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.instrument_make_qty(instrument_id, volume),
            )
        else:
            # 限价单
            order = self.order_factory.limit(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.instrument_make_qty(instrument_id, volume),
                price=self.instrument_make_price(instrument_id, price),
            )
        
        self.submit_order(order)
        return order.client_order_id.value
    
    def sell(self, symbol: str, price: Optional[float] = None,
             volume: Optional[float] = None) -> str:
        """
        卖出
        
        Args:
            symbol: 交易品种标识
            price: 价格（None 表示市价）
            volume: 数量
            
        Returns:
            订单ID
        """
        if volume is None:
            volume = self._config.max_position_size
        
        instrument_id = InstrumentId.from_str(symbol)
        
        if price is None:
            # 市价单
            order = self.order_factory.market(
                instrument_id=instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.instrument_make_qty(instrument_id, volume),
            )
        else:
            # 限价单
            order = self.order_factory.limit(
                instrument_id=instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.instrument_make_qty(instrument_id, volume),
                price=self.instrument_make_price(instrument_id, price),
            )
        
        self.submit_order(order)
        return order.client_order_id.value
    
    def get_position_size(self, symbol: str) -> float:
        """
        获取持仓数量
        
        Args:
            symbol: 交易品种标识
            
        Returns:
            持仓数量（正数为多头，负数为空头，0为无持仓）
        """
        instrument_id = InstrumentId.from_str(symbol)
        position = self.portfolio.position(instrument_id)
        
        if position is None:
            return 0.0
        
        return float(position.quantity)
    
    def has_position(self, symbol: str) -> bool:
        """
        检查是否有持仓
        
        Args:
            symbol: 交易品种标识
            
        Returns:
            是否有持仓
        """
        return self.get_position_size(symbol) != 0
    
    def is_in_cooldown(self, symbol: str) -> bool:
        """
        检查是否在冷却期
        
        Args:
            symbol: 交易品种标识
            
        Returns:
            是否在冷却期
        """
        if symbol not in self._cooldowns:
            return False
        
        cooldown_end = self._cooldowns[symbol]
        return datetime.now() < cooldown_end
    
    def set_cooldown(self, symbol: str, seconds: int = 3600):
        """
        设置冷却期
        
        Args:
            symbol: 交易品种标识
            seconds: 冷却时间（秒），默认3600秒
        """
        self._cooldowns[symbol] = datetime.now() + timedelta(seconds=seconds)
    

    
    def calculate_pnl(self, entry_price: float, exit_price: float,
                     size: float, direction: str) -> float:
        """
        计算盈亏
        
        Args:
            entry_price: 入场价格
            exit_price: 出场价格
            size: 数量
            direction: 方向 ('buy' 或 'sell')
            
        Returns:
            盈亏金额
        """
        if direction == 'buy':
            return (exit_price - entry_price) * size
        else:
            return (entry_price - exit_price) * size
    
    def on_order_filled(self, event):
        """
        订单成交回调
        
        Args:
            event: 成交事件
        """
        # 更新交易统计
        self.total_trades += 1
        
        # 计算盈亏
        if hasattr(event, 'realized_pnl'):
            pnl = float(event.realized_pnl)
            self.total_pnl += pnl
            if pnl > 0:
                self.winning_trades += 1
        
        logger.info(f"订单成交: {event.client_order_id}, "
                   f"盈亏: {getattr(event, 'realized_pnl', 0)}")


# 向后兼容：保留 StrategyBase 作为别名
class StrategyBase(Strategy):
    """
    策略基类（向后兼容）
    
    此类已弃用，请使用 Strategy 类
    """
    
    def __init__(self, params: Dict[str, Any]):
        warnings.warn(
            "StrategyBase 已弃用，请使用 Strategy 类",
            DeprecationWarning,
            stacklevel=2
        )
        
        # 转换旧版参数为新版配置
        config = StrategyConfig(
            stop_loss=params.get('stop_loss', 0.05),
            take_profit=params.get('take_profit', 0.1),
            max_position_size=params.get('max_position_size', 1.0),
            max_open_positions=params.get('max_open_positions', 5),
            entry_timeout=params.get('entry_timeout', 300),
            exit_timeout=params.get('exit_timeout', 300),
            cooldown_period=params.get('cooldown_period', 3600),
            max_drawdown=params.get('max_drawdown', 0.1),
            contract_type=params.get('contract_type', 'spot'),
            price_precision=params.get('price_precision', 8),
            size_precision=params.get('size_precision', 3),
            leverage_enabled=params.get('leverage_enabled', False),
            default_leverage=params.get('default_leverage', 1.0),
            max_leverage=params.get('max_leverage', 10.0),
        )
        
        super().__init__(config)
        self.params = params
