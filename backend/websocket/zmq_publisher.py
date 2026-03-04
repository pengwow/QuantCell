# WebSocket ZMQ 发布器
# 用于跨进程消息广播

import zmq
import zmq.asyncio
import asyncio
import json
from typing import Optional, Dict, Any
from loguru import logger


class ZMQWebSocketPublisher:
    """ZMQ WebSocket 发布器
    
    用于子进程向主进程发送 WebSocket 消息
    主进程接收后广播给 WebSocket 客户端
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, publish_port: int = 5558, subscribe_port: int = 5559):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.publish_port = publish_port
        self.subscribe_port = subscribe_port
        self._context: Optional[zmq.asyncio.Context] = None
        self._publisher: Optional[zmq.asyncio.Socket] = None
        self._subscriber: Optional[zmq.asyncio.Socket] = None
        self._running = False
        self._message_handlers = []
        
    async def start_publisher(self):
        """启动发布端（子进程使用）"""
        try:
            self._context = zmq.asyncio.Context()
            self._publisher = self._context.socket(zmq.PUSH)
            self._publisher.setsockopt(zmq.LINGER, 0)
            self._publisher.connect(f"tcp://127.0.0.1:{self.subscribe_port}")
            logger.info(f"ZMQ 发布器已连接到端口 {self.subscribe_port}")
            return True
        except Exception as e:
            logger.error(f"启动 ZMQ 发布器失败: {e}")
            return False
    
    async def start_subscriber(self, message_handler=None):
        """启动订阅端（主进程使用）"""
        try:
            self._context = zmq.asyncio.Context()
            self._subscriber = self._context.socket(zmq.PULL)
            self._subscriber.setsockopt(zmq.LINGER, 0)
            self._subscriber.bind(f"tcp://127.0.0.1:{self.subscribe_port}")
            logger.info(f"ZMQ 订阅器已绑定到端口 {self.subscribe_port}")
            
            self._running = True
            if message_handler:
                self._message_handlers.append(message_handler)
            
            # 启动接收循环
            asyncio.create_task(self._receive_loop())
            return True
        except Exception as e:
            logger.error(f"启动 ZMQ 订阅器失败: {e}")
            return False
    
    async def _receive_loop(self):
        """接收循环（主进程）"""
        while self._running:
            try:
                if self._subscriber:
                    # 使用 poll 避免阻塞
                    if await self._subscriber.poll(timeout=100):
                        data = await self._subscriber.recv_json()
                        logger.debug(f"ZMQ 收到消息: {data}")
                        
                        # 调用所有消息处理器
                        for handler in self._message_handlers:
                            try:
                                await handler(data)
                            except Exception as e:
                                logger.error(f"消息处理器错误: {e}")
                    else:
                        await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"ZMQ 接收错误: {e}")
                await asyncio.sleep(0.1)
    
    async def publish(self, message: Dict[str, Any]) -> bool:
        """发布消息（子进程使用）"""
        try:
            if self._publisher:
                await self._publisher.send_json(message)
                return True
        except Exception as e:
            logger.error(f"ZMQ 发布消息失败: {e}")
        return False
    
    def register_handler(self, handler):
        """注册消息处理器"""
        self._message_handlers.append(handler)
    
    async def stop(self):
        """停止发布器"""
        self._running = False
        
        if self._publisher:
            self._publisher.close()
        if self._subscriber:
            self._subscriber.close()
        if self._context:
            self._context.term()
        
        logger.info("ZMQ 发布器已停止")


# 全局发布器实例
zmq_publisher = ZMQWebSocketPublisher()
