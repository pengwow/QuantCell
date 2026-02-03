# 持仓管理器
# 借鉴 Freqtrade 的持仓管理机制

from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger


class PositionManager:
    """
    持仓管理器
    
    功能：
    - 开仓
    - 平仓
    - 持仓跟踪
    - 持仓统计
    """
    
    def __init__(self, strategy):
        """
        初始化持仓管理器
        
        参数：
        - strategy: 策略实例
        """
        self.strategy = strategy
        self.positions = {}
        self.position_id_counter = 0
        
        # 持仓限制配置
        self.max_open_positions = strategy.params.get('max_open_positions', 5)
        self.max_position_size = strategy.params.get('max_position_size', 1.0)
        
        # 持仓统计
        self.total_opened = 0
        self.total_closed = 0
        
        logger.info("持仓管理器初始化完成")
    
    def open_position(self, symbol: str, direction: str, 
                   price: float, volume: float) -> Optional[Dict[str, Any]]:
        """
        开仓
        
        参数：
        - symbol: 交易对
        - direction: 方向（long, short）
        - price: 开仓价格
        - volume: 开仓数量
        
        返回：
        - dict: 持仓信息，如果失败返回 None
        """
        # 检查最大持仓数
        if len(self.positions) >= self.max_open_positions:
            logger.warning(f"已达到最大持仓数: {self.max_open_positions}")
            return None
        
        # 检查最大仓位大小
        if volume > self.max_position_size:
            logger.warning(f"开仓数量 {volume} 超过最大值 {self.max_position_size}")
            return None
        
        self.position_id_counter += 1
        
        position = {
            'position_id': str(self.position_id_counter),
            'symbol': symbol,
            'direction': direction,
            'entry_price': price,
            'current_price': price,
            'volume': volume,
            'status': 'open',
            'opened_at': datetime.now(),
            'updated_at': datetime.now(),
            'unrealized_pnl': 0.0,
            'realized_pnl': 0.0
        }
        
        position_key = f"{symbol}_{direction}"
        self.positions[position_key] = position
        self.total_opened += 1
        
        logger.info(f"持仓已开: {position['position_id']}, 方向: {direction}, 价格: {price}, 数量: {volume}")
        
        return position
    
    def close_position(self, symbol: str, direction: str, 
                    price: float, volume: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        平仓
        
        参数：
        - symbol: 交易对
        - direction: 方向（long, short）
        - price: 平仓价格
        - volume: 平仓数量（可选，默认为全部）
        
        返回：
        - dict: 持仓信息，如果失败返回 None
        """
        position_key = f"{symbol}_{direction}"
        
        if position_key not in self.positions:
            logger.warning(f"持仓 {position_key} 不存在")
            return None
        
        position = self.positions[position_key]
        
        if position['status'] != 'open':
            logger.warning(f"持仓 {position['position_id']} 状态不是 open: {position['status']}")
            return None
        
        # 如果未指定平仓数量，则平全部
        if volume is None:
            volume = position['volume']
        elif volume > position['volume']:
            logger.warning(f"平仓数量 {volume} 超过持仓数量 {position['volume']}")
            return None
        
        # 计算盈亏
        if direction == 'long':
            pnl = (price - position['entry_price']) * volume
        else:
            pnl = (position['entry_price'] - price) * volume
        
        position['status'] = 'closed'
        position['exit_price'] = price
        position['exit_volume'] = volume
        position['closed_at'] = datetime.now()
        position['updated_at'] = datetime.now()
        position['realized_pnl'] = pnl
        
        # 从持仓列表中移除
        del self.positions[position_key]
        self.total_closed += 1
        
        logger.info(f"持仓已平: {position['position_id']}, 盈亏: {pnl:.2f}")
        
        return position
    
    def update_position_price(self, symbol: str, direction: str, 
                          current_price: float) -> bool:
        """
        更新持仓价格
        
        参数：
        - symbol: 交易对
        - direction: 方向
        - current_price: 当前价格
        
        返回：
        - bool: 是否成功更新
        """
        position_key = f"{symbol}_{direction}"
        
        if position_key not in self.positions:
            return False
        
        position = self.positions[position_key]
        
        if position['status'] != 'open':
            return False
        
        # 更新当前价格
        position['current_price'] = current_price
        position['updated_at'] = datetime.now()
        
        # 计算未实现盈亏
        if position['direction'] == 'long':
            position['unrealized_pnl'] = (current_price - position['entry_price']) * position['volume']
        else:
            position['unrealized_pnl'] = (position['entry_price'] - current_price) * position['volume']
        
        return True
    
    def get_position(self, symbol: str, direction: str) -> Optional[Dict[str, Any]]:
        """
        获取持仓
        
        参数：
        - symbol: 交易对
        - direction: 方向
        
        返回：
        - dict: 持仓信息
        """
        position_key = f"{symbol}_{direction}"
        return self.positions.get(position_key)
    
    def get_positions_by_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """
        获取指定交易对的所有持仓
        
        参数：
        - symbol: 交易对
        
        返回：
        - list: 持仓列表
        """
        return [position for position in self.positions.values() if position['symbol'] == symbol]
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """
        获取所有未平仓
        
        返回：
        - list: 未平仓列表
        """
        return [position for position in self.positions.values() if position['status'] == 'open']
    
    def get_closed_positions(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取已平仓记录
        
        参数：
        - days: 天数
        
        返回：
        - list: 已平仓列表
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        return [position for position in self.positions.values() 
                if position['status'] == 'closed' and position['closed_at'] > cutoff_time]
    
    def get_position_statistics(self) -> Dict[str, Any]:
        """
        获取持仓统计信息
        
        返回：
        - dict: 统计信息
        """
        open_positions = self.get_open_positions()
        closed_positions = self.get_closed_positions()
        
        total_unrealized_pnl = sum([p['unrealized_pnl'] for p in open_positions])
        total_realized_pnl = sum([p['realized_pnl'] for p in closed_positions])
        
        return {
            'total_opened': self.total_opened,
            'total_closed': self.total_closed,
            'current_open': len(open_positions),
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_realized_pnl': total_realized_pnl,
            'max_open_positions': self.max_open_positions,
            'max_position_size': self.max_position_size
        }
    
    def close_all_positions(self, current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        平仓所有持仓
        
        参数：
        - current_prices: 当前价格字典 {symbol: price}
        
        返回：
        - list: 已平仓的持仓列表
        """
        closed_positions = []
        
        for position in list(self.get_open_positions()):
            symbol = position['symbol']
            direction = position['direction']
            
            if symbol in current_prices:
                closed = self.close_position(symbol, direction, current_prices[symbol])
                if closed:
                    closed_positions.append(closed)
        
        return closed_positions
    
    def clear_old_positions(self, keep_days: int = 30) -> int:
        """
        清理旧持仓记录
        
        参数：
        - keep_days: 保留天数
        
        返回：
        - int: 清理的持仓数量
        """
        cutoff_time = datetime.now() - timedelta(days=keep_days)
        positions_to_remove = []
        
        for position_key, position in self.positions.items():
            if position['status'] == 'closed' and position['closed_at'] < cutoff_time:
                positions_to_remove.append(position_key)
        
        for position_key in positions_to_remove:
            del self.positions[position_key]
        
        logger.info(f"已清理 {len(positions_to_remove)} 个旧持仓记录")
        return len(positions_to_remove)