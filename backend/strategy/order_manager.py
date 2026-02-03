# 订单管理器
# 借鉴 Freqtrade 的订单管理机制

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger


class OrderManager:
    """
    订单管理器
    
    功能：
    - 创建订单
    - 检查订单超时
    - 取消订单
    - 更新订单状态
    """
    
    def __init__(self, strategy):
        """
        初始化订单管理器
        
        参数：
        - strategy: 策略实例
        """
        self.strategy = strategy
        self.orders = {}
        self.order_id_counter = 0
        
        # 订单超时配置
        self.entry_timeout = strategy.params.get('entry_timeout', 300)
        self.exit_timeout = strategy.params.get('exit_timeout', 300)
        
        # 订单类型配置
        self.supported_order_types = ['limit', 'market', 'stoploss']
        
        logger.info("订单管理器初始化完成")
    
    def create_order(self, symbol: str, direction: str, 
                   price: float, volume: float, 
                   order_type: str = 'limit') -> Dict[str, Any]:
        """
        创建订单
        
        参数：
        - symbol: 交易对
        - direction: 方向（buy, sell, long, short, cover, close_short）
        - price: 价格
        - volume: 数量
        - order_type: 订单类型（limit, market, stoploss）
        
        返回：
        - dict: 订单信息
        """
        self.order_id_counter += 1
        
        order = {
            'order_id': str(self.order_id_counter),
            'symbol': symbol,
            'direction': direction,
            'price': price,
            'volume': volume,
            'order_type': order_type,
            'status': 'open',
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'timeout_at': datetime.now() + timedelta(seconds=self.entry_timeout)
        }
        
        self.orders[order['order_id']] = order
        logger.info(f"订单已创建: {order['order_id']}, 方向: {direction}, 价格: {price}, 数量: {volume}, 类型: {order_type}")
        
        return order
    
    def check_order_timeout(self, order: Dict[str, Any]) -> bool:
        """
        检查订单超时
        
        参数：
        - order: 订单信息
        
        返回：
        - bool: 是否超时
        """
        if order['status'] == 'open':
            created_at = order['created_at']
            timeout_at = order.get('timeout_at', created_at + timedelta(seconds=self.entry_timeout))
            
            if datetime.now() > timeout_at:
                logger.warning(f"订单 {order['order_id']} 超时，取消订单")
                self.cancel_order(order['order_id'])
                return True
        
        return False
    
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单
        
        参数：
        - order_id: 订单 ID
        
        返回：
        - bool: 是否成功取消
        """
        if order_id not in self.orders:
            logger.warning(f"订单 {order_id} 不存在")
            return False
        
        order = self.orders[order_id]
        if order['status'] == 'filled':
            logger.warning(f"订单 {order_id} 已成交，无法取消")
            return False
        
        order['status'] = 'cancelled'
        order['updated_at'] = datetime.now()
        logger.info(f"订单 {order_id} 已取消")
        
        return True
    
    def update_order_status(self, order_id: str, status: str, 
                        fill_price: Optional[float] = None,
                        fill_volume: Optional[float] = None) -> bool:
        """
        更新订单状态
        
        参数：
        - order_id: 订单 ID
        - status: 新状态（open, filled, partially_filled, cancelled, rejected）
        - fill_price: 成交价格
        - fill_volume: 成交数量
        
        返回：
        - bool: 是否成功更新
        """
        if order_id not in self.orders:
            logger.warning(f"订单 {order_id} 不存在")
            return False
        
        order = self.orders[order_id]
        order['status'] = status
        order['updated_at'] = datetime.now()
        
        if fill_price is not None:
            order['fill_price'] = fill_price
        if fill_volume is not None:
            order['fill_volume'] = fill_volume
        
        logger.info(f"订单 {order_id} 状态已更新: {status}")
        
        return True
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        获取订单
        
        参数：
        - order_id: 订单 ID
        
        返回：
        - dict: 订单信息
        """
        return self.orders.get(order_id)
    
    def get_orders_by_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """
        获取指定交易对的所有订单
        
        参数：
        - symbol: 交易对
        
        返回：
        - list: 订单列表
        """
        return [order for order in self.orders.values() if order['symbol'] == symbol]
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        获取所有未成交订单
        
        返回：
        - list: 未成交订单列表
        """
        return [order for order in self.orders.values() if order['status'] == 'open']
    
    def get_filled_orders(self) -> List[Dict[str, Any]]:
        """
        获取所有已成交订单
        
        返回：
        - list: 已成交订单列表
        """
        return [order for order in self.orders.values() if order['status'] == 'filled']
    
    def check_all_timeouts(self) -> List[str]:
        """
        检查所有订单的超时
        
        返回：
        - list: 超时的订单 ID 列表
        """
        timeout_orders = []
        
        for order_id, order in self.orders.items():
            if self.check_order_timeout(order):
                timeout_orders.append(order_id)
        
        return timeout_orders
    
    def get_order_statistics(self) -> Dict[str, Any]:
        """
        获取订单统计信息
        
        返回：
        - dict: 统计信息
        """
        total_orders = len(self.orders)
        open_orders = len(self.get_open_orders())
        filled_orders = len(self.get_filled_orders())
        cancelled_orders = len([order for order in self.orders.values() if order['status'] == 'cancelled'])
        
        return {
            'total_orders': total_orders,
            'open_orders': open_orders,
            'filled_orders': filled_orders,
            'cancelled_orders': cancelled_orders,
            'fill_rate': filled_orders / total_orders if total_orders > 0 else 0.0
        }
    
    def clear_completed_orders(self, keep_days: int = 7) -> int:
        """
        清理已完成的订单
        
        参数：
        - keep_days: 保留天数
        
        返回：
        - int: 清理的订单数量
        """
        cutoff_time = datetime.now() - timedelta(days=keep_days)
        orders_to_remove = []
        
        for order_id, order in self.orders.items():
            if order['status'] in ['filled', 'cancelled'] and order['updated_at'] < cutoff_time:
                orders_to_remove.append(order_id)
        
        for order_id in orders_to_remove:
            del self.orders[order_id]
        
        logger.info(f"已清理 {len(orders_to_remove)} 个旧订单")
        return len(orders_to_remove)