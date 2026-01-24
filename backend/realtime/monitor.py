# 监控逻辑
import time
from typing import Dict, Any, Optional
from loguru import logger


class RealtimeMonitor:
    """实时引擎监控器，负责监控引擎的运行状态和性能指标"""
    
    def __init__(self, interval: int = 30):
        """
        初始化监控器
        
        Args:
            interval: 监控间隔（秒）
        """
        self.interval = interval
        self.start_time = 0
        self.last_monitor_time = 0
        
        # 统计信息
        self.stats = {
            # 连接统计
            'total_connections': 0,
            'successful_connections': 0,
            'failed_connections': 0,
            
            # 消息统计
            'total_messages': 0,
            'processed_messages': 0,
            'failed_messages': 0,
            
            # 数据类型统计
            'data_type_stats': {},
            
            # 性能统计
            'average_processing_time': 0,
            'max_processing_time': 0,
            'min_processing_time': float('inf'),
            'processing_times': [],
            
            # 消费者统计
            'consumer_stats': {},
        }
        
        # 运行状态
        self.running = False
    
    def start(self) -> bool:
        """
        启动监控器
        
        Returns:
            bool: 启动是否成功
        """
        if self.running:
            logger.warning("监控器已在运行")
            return False
        
        logger.info("正在启动实时引擎监控器")
        self.start_time = time.time()
        self.last_monitor_time = time.time()
        self.running = True
        
        # 重置统计信息
        self.reset_stats()
        
        logger.info("实时引擎监控器启动成功")
        return True
    
    def stop(self) -> bool:
        """
        停止监控器
        
        Returns:
            bool: 停止是否成功
        """
        if not self.running:
            logger.warning("监控器未在运行")
            return False
        
        logger.info("正在停止实时引擎监控器")
        self.running = False
        
        # 输出最终统计信息
        final_stats = self.get_stats()
        logger.info(f"实时引擎监控器已停止，最终统计信息: {final_stats}")
        
        return True
    
    def reset_stats(self) -> None:
        """
        重置统计信息
        """
        self.stats = {
            'total_connections': 0,
            'successful_connections': 0,
            'failed_connections': 0,
            'total_messages': 0,
            'processed_messages': 0,
            'failed_messages': 0,
            'data_type_stats': {},
            'average_processing_time': 0,
            'max_processing_time': 0,
            'min_processing_time': float('inf'),
            'processing_times': [],
            'consumer_stats': {},
        }
    
    def record_connection(self, success: bool) -> None:
        """
        记录连接事件
        
        Args:
            success: 连接是否成功
        """
        self.stats['total_connections'] += 1
        if success:
            self.stats['successful_connections'] += 1
        else:
            self.stats['failed_connections'] += 1
    
    def record_message(self, data_type: str, success: bool, processing_time: float = 0) -> None:
        """
        记录消息处理事件
        
        Args:
            data_type: 数据类型
            success: 处理是否成功
            processing_time: 处理时间（秒）
        """
        self.stats['total_messages'] += 1
        if success:
            self.stats['processed_messages'] += 1
        else:
            self.stats['failed_messages'] += 1
        
        # 更新数据类型统计
        if data_type not in self.stats['data_type_stats']:
            self.stats['data_type_stats'][data_type] = {
                'total': 0,
                'successful': 0,
                'failed': 0
            }
        
        self.stats['data_type_stats'][data_type]['total'] += 1
        if success:
            self.stats['data_type_stats'][data_type]['successful'] += 1
        else:
            self.stats['data_type_stats'][data_type]['failed'] += 1
        
        # 更新性能统计
        if processing_time > 0:
            self.stats['processing_times'].append(processing_time)
            self.stats['average_processing_time'] = sum(self.stats['processing_times']) / len(self.stats['processing_times'])
            self.stats['max_processing_time'] = max(self.stats['max_processing_time'], processing_time)
            self.stats['min_processing_time'] = min(self.stats['min_processing_time'], processing_time)
    
    def record_consumer_event(self, consumer_name: str, data_type: str, success: bool) -> None:
        """
        记录消费者事件
        
        Args:
            consumer_name: 消费者名称
            data_type: 数据类型
            success: 处理是否成功
        """
        if consumer_name not in self.stats['consumer_stats']:
            self.stats['consumer_stats'][consumer_name] = {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'data_types': {}
            }
        
        self.stats['consumer_stats'][consumer_name]['total'] += 1
        if success:
            self.stats['consumer_stats'][consumer_name]['successful'] += 1
        else:
            self.stats['consumer_stats'][consumer_name]['failed'] += 1
        
        # 更新消费者数据类型统计
        if data_type not in self.stats['consumer_stats'][consumer_name]['data_types']:
            self.stats['consumer_stats'][consumer_name]['data_types'][data_type] = {
                'total': 0,
                'successful': 0,
                'failed': 0
            }
        
        self.stats['consumer_stats'][consumer_name]['data_types'][data_type]['total'] += 1
        if success:
            self.stats['consumer_stats'][consumer_name]['data_types'][data_type]['successful'] += 1
        else:
            self.stats['consumer_stats'][consumer_name]['data_types'][data_type]['failed'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        current_time = time.time()
        uptime = current_time - self.start_time
        
        # 计算消息速率
        messages_per_second = 0
        if uptime > 0:
            messages_per_second = self.stats['total_messages'] / uptime
        
        # 计算处理速率
        processing_per_second = 0
        if uptime > 0:
            processing_per_second = self.stats['processed_messages'] / uptime
        
        # 构建统计结果
        stats = {
            # 基本信息
            'uptime': uptime,
            'monitor_interval': self.interval,
            
            # 连接统计
            'connections': {
                'total': self.stats['total_connections'],
                'successful': self.stats['successful_connections'],
                'failed': self.stats['failed_connections'],
                'success_rate': 0 if self.stats['total_connections'] == 0 else \
                    self.stats['successful_connections'] / self.stats['total_connections']
            },
            
            # 消息统计
            'messages': {
                'total': self.stats['total_messages'],
                'processed': self.stats['processed_messages'],
                'failed': self.stats['failed_messages'],
                'success_rate': 0 if self.stats['total_messages'] == 0 else \
                    self.stats['processed_messages'] / self.stats['total_messages'],
                'rate': messages_per_second,
                'processing_rate': processing_per_second
            },
            
            # 数据类型统计
            'data_type_stats': self.stats['data_type_stats'],
            
            # 性能统计
            'performance': {
                'average_processing_time': self.stats['average_processing_time'] * 1000,  # 转换为毫秒
                'max_processing_time': self.stats['max_processing_time'] * 1000,  # 转换为毫秒
                'min_processing_time': self.stats['min_processing_time'] * 1000 if self.stats['min_processing_time'] != float('inf') else 0,  # 转换为毫秒
                'processing_count': len(self.stats['processing_times'])
            },
            
            # 消费者统计
            'consumer_stats': self.stats['consumer_stats'],
        }
        
        return stats
    
    def monitor(self) -> None:
        """
        执行监控逻辑，定期输出监控报告
        """
        if not self.running:
            return
        
        current_time = time.time()
        if current_time - self.last_monitor_time >= self.interval:
            # 获取统计信息
            stats = self.get_stats()
            
            # 输出监控报告
            self._output_monitor_report(stats)
            
            # 更新最后监控时间
            self.last_monitor_time = current_time
    
    def _output_monitor_report(self, stats: Dict[str, Any]) -> None:
        """
        输出监控报告
        
        Args:
            stats: 统计信息
        """
        logger.info("=== 实时引擎监控报告 ===")
        logger.info(f"运行时间: {stats['uptime']:.2f} 秒")
        
        # 连接统计
        connections = stats['connections']
        logger.info(f"连接统计: 总数={connections['total']}, 成功={connections['successful']}, 失败={connections['failed']}, 成功率={connections['success_rate']:.2%}")
        
        # 消息统计
        messages = stats['messages']
        logger.info(f"消息统计: 总数={messages['total']}, 处理成功={messages['processed']}, 处理失败={messages['failed']}, 成功率={messages['success_rate']:.2%}")
        logger.info(f"消息速率: {messages['rate']:.2f} 条/秒, 处理速率: {messages['processing_rate']:.2f} 条/秒")
        
        # 性能统计
        performance = stats['performance']
        logger.info(f"性能统计: 平均处理时间={performance['average_processing_time']:.2f} 毫秒, 最大={performance['max_processing_time']:.2f} 毫秒, 最小={performance['min_processing_time']:.2f} 毫秒")
        
        # 数据类型统计
        data_type_stats = stats['data_type_stats']
        if data_type_stats:
            logger.info("数据类型统计:")
            for data_type, data_stats in data_type_stats.items():
                success_rate = 0
                if data_stats['total'] > 0:
                    success_rate = data_stats['successful'] / data_stats['total']
                logger.info(f"  {data_type}: 总数={data_stats['total']}, 成功={data_stats['successful']}, 失败={data_stats['failed']}, 成功率={success_rate:.2%}")
        
        # 消费者统计
        consumer_stats = stats['consumer_stats']
        if consumer_stats:
            logger.info("消费者统计:")
            for consumer_name, consumer_data in consumer_stats.items():
                success_rate = 0
                if consumer_data['total'] > 0:
                    success_rate = consumer_data['successful'] / consumer_data['total']
                logger.info(f"  {consumer_name}: 总数={consumer_data['total']}, 成功={consumer_data['successful']}, 失败={consumer_data['failed']}, 成功率={success_rate:.2%}")
        
        logger.info("====================")
    
    def get_alert(self) -> Optional[Dict[str, Any]]:
        """
        获取告警信息
        
        Returns:
            Optional[Dict[str, Any]]: 告警信息，None表示无告警
        """
        stats = self.get_stats()
        
        # 检查连接成功率
        connections = stats['connections']
        if connections['total'] > 10 and connections['success_rate'] < 0.8:
            return {
                'level': 'warning',
                'message': f"连接成功率过低: {connections['success_rate']:.2%}",
                'metric': 'connection_success_rate',
                'value': connections['success_rate'],
                'threshold': 0.8
            }
        
        # 检查消息处理成功率
        messages = stats['messages']
        if messages['total'] > 100 and messages['success_rate'] < 0.9:
            return {
                'level': 'warning',
                'message': f"消息处理成功率过低: {messages['success_rate']:.2%}",
                'metric': 'message_success_rate',
                'value': messages['success_rate'],
                'threshold': 0.9
            }
        
        # 检查平均处理时间
        performance = stats['performance']
        if performance['average_processing_time'] > 100:
            return {
                'level': 'warning',
                'message': f"平均处理时间过长: {performance['average_processing_time']:.2f} 毫秒",
                'metric': 'average_processing_time',
                'value': performance['average_processing_time'],
                'threshold': 100
            }
        
        return None