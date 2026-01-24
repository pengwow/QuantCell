# WebSocket连接管理器
import asyncio
from typing import Dict, List, Any, Optional, Callable
from loguru import logger
from .abstract_client import AbstractExchangeClient


class WebSocketManager:
    """WebSocket连接管理器，负责管理多个交易所客户端的连接和消息处理"""
    
    def __init__(self):
        """初始化WebSocket连接管理器"""
        self.clients: Dict[str, AbstractExchangeClient] = {}
        self.message_handlers: List[Callable[[Dict[str, Any]], None]] = []
        self.running = False
        self.task = None
        self.reconnect_task = None
    
    def register_client(self, client: AbstractExchangeClient) -> bool:
        """
        注册交易所客户端
        
        Args:
            client: 交易所客户端实例
        
        Returns:
            bool: 注册是否成功
        """
        exchange_name = client.exchange_name
        if exchange_name in self.clients:
            logger.warning(f"交易所客户端已存在: {exchange_name}")
            return False
        
        self.clients[exchange_name] = client
        logger.info(f"成功注册交易所客户端: {exchange_name}")
        return True
    
    def unregister_client(self, exchange_name: str) -> bool:
        """
        注销交易所客户端
        
        Args:
            exchange_name: 交易所名称
        
        Returns:
            bool: 注销是否成功
        """
        if exchange_name not in self.clients:
            logger.warning(f"交易所客户端不存在: {exchange_name}")
            return False
        
        # 断开连接
        asyncio.create_task(self._disconnect_client(exchange_name))
        
        # 从客户端列表中移除
        del self.clients[exchange_name]
        logger.info(f"成功注销交易所客户端: {exchange_name}")
        return True
    
    async def _disconnect_client(self, exchange_name: str) -> None:
        """
        断开客户端连接（异步）
        
        Args:
            exchange_name: 交易所名称
        """
        if exchange_name in self.clients:
            client = self.clients[exchange_name]
            await client.disconnect()
    
    def add_message_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        添加消息处理器
        
        Args:
            handler: 消息处理函数
        """
        self.message_handlers.append(handler)
        logger.info(f"成功添加消息处理器")
    
    def remove_message_handler(self, handler: Callable[[Dict[str, Any]], None]) -> bool:
        """
        移除消息处理器
        
        Args:
            handler: 消息处理函数
        
        Returns:
            bool: 移除是否成功
        """
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)
            logger.info(f"成功移除消息处理器")
            return True
        
        logger.warning(f"消息处理器不存在")
        return False
    
    async def connect_all(self) -> bool:
        """
        连接所有注册的客户端
        
        Returns:
            bool: 所有客户端是否都连接成功
        """
        logger.info(f"正在连接所有交易所客户端，共 {len(self.clients)} 个")
        
        tasks = [client.connect() for client in self.clients.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for i, result in enumerate(results):
            if isinstance(result, bool) and result:
                success_count += 1
            else:
                exchange_name = list(self.clients.keys())[i]
                logger.error(f"连接交易所客户端失败: {exchange_name}, 错误: {result}")
        
        logger.info(f"连接完成，成功 {success_count} 个，失败 {len(results) - success_count} 个")
        return success_count == len(results)
    
    async def disconnect_all(self) -> bool:
        """
        断开所有注册的客户端连接
        
        Returns:
            bool: 所有客户端是否都断开成功
        """
        logger.info(f"正在断开所有交易所客户端连接，共 {len(self.clients)} 个")
        
        tasks = [client.disconnect() for client in self.clients.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for i, result in enumerate(results):
            if isinstance(result, bool) and result:
                success_count += 1
            else:
                exchange_name = list(self.clients.keys())[i]
                logger.error(f"断开交易所客户端连接失败: {exchange_name}, 错误: {result}")
        
        logger.info(f"断开连接完成，成功 {success_count} 个，失败 {len(results) - success_count} 个")
        return success_count == len(results)
    
    async def _process_messages(self) -> None:
        """
        异步处理消息，从所有客户端接收消息并分发给处理器
        """
        while self.running:
            if not self.clients:
                await asyncio.sleep(1)
                continue
            
            # 从所有客户端接收消息
            tasks = [client.receive_message() for client in self.clients.values()]
            messages = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理收到的消息
            for i, message in enumerate(messages):
                if isinstance(message, Exception):
                    exchange_name = list(self.clients.keys())[i]
                    logger.error(f"接收消息失败: {exchange_name}, 错误: {message}")
                elif message:
                    # 分发给所有消息处理器
                    for handler in self.message_handlers:
                        try:
                            handler(message)
                        except Exception as e:
                            logger.error(f"消息处理器执行失败: {e}")
            
            # 短暂休眠，避免CPU占用过高
            await asyncio.sleep(0.01)
    
    async def _monitor_connections(self) -> None:
        """
        监控客户端连接状态，自动重连
        """
        while self.running:
            for exchange_name, client in self.clients.items():
                if not client.is_connected:
                    logger.warning(f"交易所客户端连接已断开: {exchange_name}, 尝试重连")
                    await client.connect()
            
            # 每30秒检查一次连接状态
            await asyncio.sleep(30)
    
    async def start(self) -> bool:
        """
        启动WebSocket连接管理器
        
        Returns:
            bool: 启动是否成功
        """
        if self.running:
            logger.warning("WebSocket连接管理器已在运行")
            return False
        
        logger.info("正在启动WebSocket连接管理器")
        
        # 连接所有客户端
        await self.connect_all()
        
        # 设置运行标志
        self.running = True
        
        # 启动消息处理任务
        self.task = asyncio.create_task(self._process_messages())
        
        # 启动连接监控任务
        self.reconnect_task = asyncio.create_task(self._monitor_connections())
        
        logger.info("WebSocket连接管理器启动成功")
        return True
    
    async def stop(self) -> bool:
        """
        停止WebSocket连接管理器
        
        Returns:
            bool: 停止是否成功
        """
        if not self.running:
            logger.warning("WebSocket连接管理器未在运行")
            return False
        
        logger.info("正在停止WebSocket连接管理器")
        
        # 设置运行标志为False
        self.running = False
        
        # 等待任务完成
        if self.task:
            await asyncio.wait_for(self.task, timeout=5)
            self.task = None
        
        if self.reconnect_task:
            await asyncio.wait_for(self.reconnect_task, timeout=5)
            self.reconnect_task = None
        
        # 断开所有客户端连接
        await self.disconnect_all()
        
        logger.info("WebSocket连接管理器停止成功")
        return True
    
    async def restart(self) -> bool:
        """
        重启WebSocket连接管理器
        
        Returns:
            bool: 重启是否成功
        """
        logger.info("正在重启WebSocket连接管理器")
        
        # 停止当前运行的管理器
        await self.stop()
        
        # 启动管理器
        return await self.start()
    
    def get_client(self, exchange_name: str) -> Optional[AbstractExchangeClient]:
        """
        获取指定交易所的客户端
        
        Args:
            exchange_name: 交易所名称
        
        Returns:
            Optional[AbstractExchangeClient]: 交易所客户端实例，None表示不存在
        """
        return self.clients.get(exchange_name)
    
    def get_connected_clients(self) -> List[str]:
        """
        获取已连接的客户端列表
        
        Returns:
            List[str]: 已连接的交易所名称列表
        """
        connected = []
        for exchange_name, client in self.clients.items():
            if client.is_connected:
                connected.append(exchange_name)
        return connected
    
    def get_all_clients(self) -> List[str]:
        """
        获取所有注册的客户端列表
        
        Returns:
            List[str]: 所有交易所名称列表
        """
        return list(self.clients.keys())