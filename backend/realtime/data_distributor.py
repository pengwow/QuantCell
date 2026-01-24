# 数据分发器
from typing import Dict, Any, List, Callable, Optional
from loguru import logger


class DataDistributor:
    """数据分发器，负责将处理后的数据分发给不同的消费者"""
    
    def __init__(self):
        """初始化数据分发器"""
        self.consumers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
    
    def register_consumer(self, data_type: str, consumer: Callable[[Dict[str, Any]], None]) -> bool:
        """
        注册数据消费者
        
        Args:
            data_type: 数据类型，如'kline', 'depth'等
            consumer: 消费者回调函数
        
        Returns:
            bool: 注册是否成功
        """
        if data_type not in self.consumers:
            self.consumers[data_type] = []
        
        self.consumers[data_type].append(consumer)
        logger.info(f"成功注册消费者，数据类型: {data_type}")
        return True
    
    def unregister_consumer(self, data_type: str, consumer: Callable[[Dict[str, Any]], None]) -> bool:
        """
        注销数据消费者
        
        Args:
            data_type: 数据类型，如'kline', 'depth'等
            consumer: 消费者回调函数
        
        Returns:
            bool: 注销是否成功
        """
        if data_type not in self.consumers:
            logger.warning(f"数据类型不存在: {data_type}")
            return False
        
        if consumer not in self.consumers[data_type]:
            logger.warning(f"消费者不存在: {consumer}")
            return False
        
        self.consumers[data_type].remove(consumer)
        logger.info(f"成功注销消费者，数据类型: {data_type}")
        return True
    
    def distribute(self, data: Dict[str, Any]) -> bool:
        """
        分发数据给对应的消费者
        
        Args:
            data: 待分发的数据
        
        Returns:
            bool: 分发是否成功
        """
        try:
            # 获取数据类型
            data_type = data.get('data_type', '')
            if not data_type:
                logger.warning("数据缺少类型字段")
                return False
            
            # 分发给所有注册的消费者
            if data_type in self.consumers:
                for consumer in self.consumers[data_type]:
                    try:
                        consumer(data)
                    except Exception as e:
                        logger.error(f"消费者执行失败: {e}")
            
            # 分发给所有数据类型的消费者
            if '*' in self.consumers:
                for consumer in self.consumers['*']:
                    try:
                        consumer(data)
                    except Exception as e:
                        logger.error(f"通用消费者执行失败: {e}")
            
            return True
        
        except Exception as e:
            logger.error(f"数据分发失败: {e}")
            return False
    
    def broadcast(self, data: Dict[str, Any]) -> bool:
        """
        广播数据给所有消费者（包括通用消费者）
        
        Args:
            data: 待广播的数据
        
        Returns:
            bool: 广播是否成功
        """
        try:
            # 分发给所有消费者
            for data_type in self.consumers:
                for consumer in self.consumers[data_type]:
                    try:
                        consumer(data)
                    except Exception as e:
                        logger.error(f"消费者执行失败: {e}")
            
            return True
        
        except Exception as e:
            logger.error(f"数据广播失败: {e}")
            return False
    
    def get_consumer_count(self, data_type: str = None) -> int:
        """
        获取消费者数量
        
        Args:
            data_type: 数据类型，如'kline', 'depth'等，None表示所有类型
        
        Returns:
            int: 消费者数量
        """
        if data_type:
            return len(self.consumers.get(data_type, []))
        else:
            total = 0
            for consumers in self.consumers.values():
                total += len(consumers)
            return total
    
    def clear_consumers(self, data_type: str = None) -> bool:
        """
        清除消费者
        
        Args:
            data_type: 数据类型，如'kline', 'depth'等，None表示所有类型
        
        Returns:
            bool: 清除是否成功
        """
        try:
            if data_type:
                if data_type in self.consumers:
                    del self.consumers[data_type]
            else:
                self.consumers.clear()
            
            logger.info(f"成功清除消费者，数据类型: {data_type}")
            return True
        
        except Exception as e:
            logger.error(f"清除消费者失败: {e}")
            return False
