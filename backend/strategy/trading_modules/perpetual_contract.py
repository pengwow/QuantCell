# 加密货币支持模块
# 支持现货和永续合约

from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP
from typing import Dict, Any, Optional
from loguru import logger

getcontext().prec = 28


class PerpetualContract:
    """
    永续合约支持
    """
    
    def __init__(self, symbol: str, funding_interval: int = 8):
        """
        初始化永续合约
        
        参数：
        - symbol: 交易对符号
        - funding_interval: 资金费率间隔（小时）
        """
        self.symbol = symbol
        self.funding_interval = funding_interval
        self.funding_rates = []
        self.mark_prices = []
        self.index_prices = []
    
    def calculate_funding_rate(self, index_price: float, 
                           mark_price: float) -> float:
        """
        计算资金费率
        
        参数：
        - index_price: 指数价格
        - mark_price: 标记价格
        
        返回：
        - float: 资金费率
        """
        funding_rate = (mark_price - index_price) / index_price
        
        # 限制在 ±0.75% 之间
        funding_rate = max(min(funding_rate, 0.0075), -0.0075)
        
        return funding_rate
    
    def calculate_funding_payment(self, position_size: float, 
                              funding_rate: float) -> float:
        """
        计算资金费支付
        
        参数：
        - position_size: 持仓大小
        - funding_rate: 资金费率
        
        返回：
        - float: 资金费支付金额
        """
        return position_size * funding_rate
    
    def should_rebalance(self, current_time: float, 
                      last_funding_time: float) -> bool:
        """
        判断是否需要调仓
        
        参数：
        - current_time: 当前时间
        - last_funding_time: 上次资金费时间
        
        返回：
        - bool: 是否需要调仓
        """
        time_diff = current_time - last_funding_time
        return time_diff >= self.funding_interval * 3600
    
    def add_funding_rate(self, funding_rate: float, mark_price: float, 
                    index_price: float, timestamp: float):
        """
        添加资金费率记录
        
        参数：
        - funding_rate: 资金费率
        - mark_price: 标记价格
        - index_price: 指数价格
        - timestamp: 时间戳
        """
        self.funding_rates.append(funding_rate)
        self.mark_prices.append(mark_price)
        self.index_prices.append(index_price)
        logger.info(f"资金费率已添加: {funding_rate:.6f}, 标记价格: {mark_price:.2f}, 指数价格: {index_price:.2f}")


class CryptoUtils:
    """
    加密货币工具类
    """
    
    def __init__(self, price_precision: int = 8, size_precision: int = 3):
        """
        初始化工具类
        
        参数：
        - price_precision: 价格精度
        - size_precision: 数量精度
        """
        self.price_precision = price_precision
        self.size_precision = size_precision
    
    def round_price(self, price: float) -> float:
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
    
    def round_size(self, size: float) -> float:
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
    
    def calculate_notional(self, price: float, size: float) -> float:
        """
        计算名义价值
        
        参数：
        - price: 价格
        - size: 数量
        
        返回：
        - float: 名义价值
        """
        return self.round_price(price) * self.round_size(size)
    
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
    
    def to_decimal(self, value: Any) -> Decimal:
        """
        转换为 Decimal（高精度）
        
        参数：
        - value: 要转换的值
        
        返回：
        - Decimal: Decimal 对象
        """
        if isinstance(value, Decimal):
            return value
        elif isinstance(value, (int, float)):
            return Decimal(str(value))
        else:
            return Decimal(str(value))
    
    def from_decimal(self, value: Decimal) -> float:
        """
        从 Decimal 转换为 float
        
        参数：
        - value: Decimal 对象
        
        返回：
        - float: 浮点数
        """
        return float(value)
