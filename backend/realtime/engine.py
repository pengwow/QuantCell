# 实时引擎核心类
import asyncio
from typing import Dict, Any, List, Optional
from loguru import logger
from .factory import ExchangeClientFactory
from .websocket_manager import WebSocketManager
from .data_processor import DataProcessor
from .data_distributor import DataDistributor
from .config import RealtimeConfig
from .monitor import RealtimeMonitor


class RealtimeEngine:
    """实时引擎核心类，整合所有组件"""
    
    def __init__(self):
        """初始化实时引擎"""
        # 组件实例
        self.factory = ExchangeClientFactory()
        self.ws_manager = WebSocketManager()
        self.data_processor = DataProcessor()
        self.data_distributor = DataDistributor()
        self.config = RealtimeConfig()
        self.monitor = RealtimeMonitor(interval=self.config.get_config('monitor_interval'))
        
        # 运行状态
        self.running = False
        
        # 初始化组件间的连接
        self._init_component_connections()
    
    def _init_component_connections(self) -> None:
        """
        初始化组件间的连接
        """
        # 注册消息处理器到WebSocket管理器
        self.ws_manager.add_message_handler(self._handle_message)
        
        # 注册监控器到数据处理器（可选，用于性能监控）
        # 注意：这里需要根据实际情况调整，可能需要修改DataProcessor来支持监控
    
    def _handle_message(self, message: Dict[str, Any]) -> None:
        """
        处理接收到的消息
        
        Args:
            message: 接收到的消息
        """
        try:
            import time
            start_time = time.time()
            
            # 记录总消息数
            self.monitor.record_message(message.get('data_type', 'unknown'), False)
            
            # 处理消息
            processed_message = self.data_processor.process_message(message)
            
            processing_time = time.time() - start_time
            
            if processed_message:
                # 记录处理成功的消息
                self.monitor.record_message(
                    processed_message.get('data_type', 'unknown'),
                    True,
                    processing_time
                )
                
                # 分发处理后的消息
                self.data_distributor.distribute(processed_message)
            else:
                # 记录处理失败的消息
                self.monitor.record_message(message.get('data_type', 'unknown'), False)
                
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            # 记录处理失败的消息
            self.monitor.record_message(message.get('data_type', 'unknown'), False)
        
        # 更新监控信息
        self.monitor.monitor()
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取实时引擎状态
        
        Returns:
            Dict[str, Any]: 实时引擎状态
        """
        # 获取WebSocket管理器状态
        connected_clients = self.ws_manager.get_connected_clients()
        
        # 获取监控统计信息
        monitor_stats = self.monitor.get_stats()
        
        return {
            "status": "running" if self.running else "stopped",
            "connected": len(connected_clients) > 0,
            "connected_exchanges": connected_clients,
            "total_exchanges": len(self.ws_manager.get_all_clients()),
            "config": self.config.get_config(),
            "stats": monitor_stats
        }
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取实时引擎配置
        
        Returns:
            Dict[str, Any]: 实时引擎配置
        """
        return self.config.get_config()
    
    def update_config(self, config_dict: Dict[str, Any]) -> bool:
        """
        更新实时引擎配置
        
        Args:
            config_dict: 配置字典
        
        Returns:
            bool: 更新是否成功
        """
        success = self.config.load_config(config_dict)
        
        if success:
            # 根据新配置更新组件
            self._update_components_config()
        
        return success
    
    def _update_components_config(self) -> None:
        """
        根据新配置更新组件
        """
        # 更新监控间隔
        self.monitor.interval = self.config.get_config('monitor_interval')
        
        # 更新其他组件配置...
    
    async def start(self) -> bool:
        """
        启动实时引擎
        
        Returns:
            bool: 启动是否成功
        """
        if self.running:
            logger.warning("实时引擎已在运行")
            return False
        
        logger.info("正在启动实时引擎")
        
        try:
            # 检查配置
            if not self.config.validate_config():
                logger.error("配置验证失败")
                return False
            
            # 启动监控器
            self.monitor.start()
            
            # 创建并注册交易所客户端
            success = await self._create_and_register_clients()
            if not success:
                logger.error("创建或注册交易所客户端失败")
                # 清理已注册的客户端和监控器
                self.monitor.stop()
                for exchange_name in list(self.ws_manager.get_all_clients()):
                    self.ws_manager.unregister_client(exchange_name)
                return False
            
            # 启动WebSocket管理器
            success = await self.ws_manager.start()
            if not success:
                logger.error("启动WebSocket管理器失败")
                # 清理已注册的客户端和监控器
                self.monitor.stop()
                for exchange_name in list(self.ws_manager.get_all_clients()):
                    self.ws_manager.unregister_client(exchange_name)
                return False
            
            # 设置运行标志
            self.running = True
            
            logger.info("实时引擎启动成功")
            return True
        
        except Exception as e:
            logger.error(f"启动实时引擎失败: {e}")
            logger.exception(e)
            await self.stop()
            return False
    
    async def _create_and_register_clients(self) -> bool:
        """
        创建并注册交易所客户端
        
        Returns:
            bool: 创建和注册是否成功
        """
        # 获取配置
        default_exchange = self.config.get_config('default_exchange')
        symbols = self.config.get_config('symbols')
        data_types = self.config.get_config('data_types')
        intervals = self.config.get_config('intervals')
        
        # 创建交易所客户端
        client = self.factory.create_client(default_exchange, self.config.get_config())
        if not client:
            logger.error(f"创建交易所客户端失败: {default_exchange}")
            return False
        
        # 注册客户端到WebSocket管理器（强制替换已存在的客户端）
        success = self.ws_manager.register_client(client, force=True)
        if not success:
            logger.error(f"注册交易所客户端失败: {default_exchange}")
            return False
        
        # 首先建立WebSocket连接
        success = await client.connect()
        if not success:
            logger.error(f"建立WebSocket连接失败: {default_exchange}")
            # 注册失败，清理客户端
            self.ws_manager.unregister_client(default_exchange)
            return False
        
        # 构建订阅频道
        channels = []
        for symbol in symbols:
            for data_type in data_types:
                if data_type == 'kline' and intervals:
                    for interval in intervals:
                        channels.append(f"{symbol}@{data_type}_{interval}")
                else:
                    channels.append(f"{symbol}@{data_type}")
        
        # 订阅频道
        success = await client.subscribe(channels)
        if not success:
            logger.error(f"订阅频道失败: {default_exchange}")
            # 订阅失败，清理客户端
            self.ws_manager.unregister_client(default_exchange)
            return False
        
        return True
    
    async def stop(self) -> bool:
        """
        停止实时引擎
        
        Returns:
            bool: 停止是否成功
        """
        if not self.running:
            logger.warning("实时引擎未在运行")
            return False
        
        logger.info("正在停止实时引擎")
        
        try:
            # 停止WebSocket管理器
            await self.ws_manager.stop()
            
            # 停止监控器
            self.monitor.stop()
            
            # 清理客户端
            for exchange_name in self.ws_manager.get_all_clients():
                self.ws_manager.unregister_client(exchange_name)
            
            # 重置运行标志
            self.running = False
            
            logger.info("实时引擎停止成功")
            return True
        
        except Exception as e:
            logger.error(f"停止实时引擎失败: {e}")
            return False
    
    async def restart(self) -> bool:
        """
        重启实时引擎
        
        Returns:
            bool: 重启是否成功
        """
        logger.info("正在重启实时引擎")
        
        # 停止引擎
        await self.stop()
        
        # 等待一段时间
        await asyncio.sleep(1)
        
        # 启动引擎
        return await self.start()
    
    async def subscribe(self, channels: List[str]) -> bool:
        """
        订阅频道
        
        Args:
            channels: 频道列表
        
        Returns:
            bool: 订阅是否成功
        """
        # 获取默认交易所客户端
        default_exchange = self.config.get_config('default_exchange')
        client = self.ws_manager.get_client(default_exchange)
        
        if not client:
            logger.error(f"获取交易所客户端失败: {default_exchange}")
            return False
        
        # 订阅频道
        return await client.subscribe(channels)
    
    async def unsubscribe(self, channels: List[str]) -> bool:
        """
        取消订阅频道
        
        Args:
            channels: 频道列表
        
        Returns:
            bool: 取消订阅是否成功
        """
        # 获取默认交易所客户端
        default_exchange = self.config.get_config('default_exchange')
        client = self.ws_manager.get_client(default_exchange)
        
        if not client:
            logger.error(f"获取交易所客户端失败: {default_exchange}")
            return False
        
        # 取消订阅频道
        return await client.unsubscribe(channels)
    
    def get_available_symbols(self) -> List[str]:
        """
        获取可用交易对
        
        Returns:
            List[str]: 可用交易对
        """
        # 这里需要根据实际情况实现，可能需要从交易所获取或从配置中读取
        return self.config.get_config('symbols')
    
    def register_consumer(self, data_type: str, consumer: callable) -> bool:
        """
        注册数据消费者
        
        Args:
            data_type: 数据类型
            consumer: 消费者回调函数
        
        Returns:
            bool: 注册是否成功
        """
        return self.data_distributor.register_consumer(data_type, consumer)
    
    def unregister_consumer(self, data_type: str, consumer: callable) -> bool:
        """
        注销数据消费者
        
        Args:
            data_type: 数据类型
            consumer: 消费者回调函数
        
        Returns:
            bool: 注销是否成功
        """
        return self.data_distributor.unregister_consumer(data_type, consumer)