# WebSocket连接管理器

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Set, Optional, Any, List

from loguru import logger

# 自定义JSON编码器，处理datetime对象
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        """初始化连接管理器"""
        # 活跃连接映射: {client_id: websocket}
        self.active_connections: Dict[str, Any] = {}
        # 订阅映射: {topic: set(client_ids)}
        self.subscriptions: Dict[str, Set[str]] = {}
        # 客户端信息映射: {client_id: client_info}
        self.client_info: Dict[str, Dict[str, Any]] = {}
        # 消息队列
        self.message_queue: asyncio.Queue = asyncio.Queue()
        # 消息处理任务
        self.processing_task: Optional[asyncio.Task] = None
        # 消息批处理配置
        self.batch_size: int = 10  # 批处理大小
        self.batch_interval: float = 0.1  # 批处理间隔（秒）
        # 客户端消息速率限制配置
        self.rate_limit: int = 100  # 每秒最大消息数
        self.rate_limit_window: int = 1  # 速率限制窗口（秒）
        # 客户端消息计数器: {client_id: [timestamp, count]}
        self.message_counters: Dict[str, List[float]] = {}
        # 批处理缓存: {client_id: List[Dict]}
        self.batch_cache: Dict[str, List[Dict[str, Any]]] = {}
    
    async def start(self):
        """启动消息处理任务"""
        self.processing_task = asyncio.create_task(self.process_messages())
        logger.info("WebSocket连接管理器已启动")
    
    async def stop(self):
        """停止消息处理任务"""
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        logger.info("WebSocket连接管理器已停止")
    
    async def connect(self, websocket: Any, client_id: Optional[str] = None, topics: Optional[Set[str]] = None):
        """处理新连接
        
        Args:
            websocket: WebSocket连接对象
            client_id: 客户端ID
            topics: 初始订阅的主题列表
        """
        # 接受连接
        await websocket.accept()
        
        # 生成客户端ID
        if not client_id:
            client_id = str(uuid.uuid4())
        
        # 保存连接
        self.active_connections[client_id] = websocket
        
        # 保存客户端信息
        self.client_info[client_id] = {
            "connected_at": datetime.now(),
            "last_ping": datetime.now(),
            "topics": set()
        }
        
        # 处理初始订阅
        if topics:
            for topic in topics:
                await self.subscribe(client_id, topic)
        
        # 发送欢迎消息
        await self.send_personal_message(
            {
                "type": "welcome",
                "id": f"welcome_{client_id}",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": {
                    "client_id": client_id,
                    "message": "Welcome to WebSocket service!"
                }
            },
            client_id
        )
        
        logger.info(f"客户端 {client_id} 已连接")
        return client_id
    
    async def disconnect(self, client_id: str):
        """处理连接断开
        
        Args:
            client_id: 客户端ID
        """
        if client_id in self.active_connections:
            # 移除连接
            del self.active_connections[client_id]
            
            # 移除客户端信息
            if client_id in self.client_info:
                del self.client_info[client_id]
            
            # 从所有订阅中移除
            # 使用 list() 创建副本，避免在遍历时修改字典
            topics_to_remove = []
            for topic, clients in list(self.subscriptions.items()):
                if client_id in clients:
                    clients.remove(client_id)
                    if not clients:
                        topics_to_remove.append(topic)
            
            # 删除空的主题订阅
            for topic in topics_to_remove:
                del self.subscriptions[topic]
            
            logger.info(f"客户端 {client_id} 已断开连接")
    
    async def subscribe(self, client_id: str, topic: str):
        """订阅主题
        
        Args:
            client_id: 客户端ID
            topic: 主题名称
        """
        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
        
        self.subscriptions[topic].add(client_id)
        
        # 更新客户端订阅信息
        if client_id in self.client_info:
            self.client_info[client_id]["topics"].add(topic)
        
        logger.debug(f"客户端 {client_id} 订阅了主题 {topic}")
        
        # 发送订阅确认
        await self.send_personal_message(
            {
                "type": "subscribe_ack",
                "id": f"sub_ack_{topic}",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": {
                    "topic": topic
                }
            },
            client_id
        )
    
    async def unsubscribe(self, client_id: str, topic: str):
        """取消订阅主题
        
        Args:
            client_id: 客户端ID
            topic: 主题名称
        """
        if topic in self.subscriptions:
            if client_id in self.subscriptions[topic]:
                self.subscriptions[topic].remove(client_id)
                if not self.subscriptions[topic]:
                    del self.subscriptions[topic]
        
        # 更新客户端订阅信息
        if client_id in self.client_info:
            if topic in self.client_info[client_id]["topics"]:
                self.client_info[client_id]["topics"].remove(topic)
        
        logger.debug(f"客户端 {client_id} 取消订阅主题 {topic}")
        
        # 发送取消订阅确认
        await self.send_personal_message(
            {
                "type": "unsubscribe_ack",
                "id": f"unsub_ack_{topic}",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": {
                    "topic": topic
                }
            },
            client_id
        )
    
    async def send_personal_message(self, message: Dict[str, Any], client_id: str):
        """发送个人消息
        
        Args:
            message: 消息内容
            client_id: 客户端ID
        """
        if client_id in self.active_connections:
            try:
                # 序列化消息中的datetime对象
                serialized_message = json.loads(json.dumps(message, cls=DateTimeEncoder))
                await self.active_connections[client_id].send_json(serialized_message)
            except Exception as e:
                logger.error(f"发送消息到客户端 {client_id} 失败: {e}")
                # 尝试断开连接
                await self.disconnect(client_id)
    
    async def broadcast(self, message: Dict[str, Any], topic: Optional[str] = None):
        """广播消息

        Args:
            message: 消息内容
            topic: 主题名称，为None时广播给所有客户端
        """
        if topic:
            # 只广播给订阅了该主题的客户端
            if topic in self.subscriptions:
                client_ids = list(self.subscriptions[topic])
                for client_id in client_ids:
                    await self.send_personal_message(message, client_id)
        else:
            # 广播给所有客户端
            client_ids = list(self.active_connections.keys())
            for client_id in client_ids:
                await self.send_personal_message(message, client_id)
    
    async def process_messages(self):
        """处理消息队列中的消息"""
        batch_timer = 0
        while True:
            try:
                # 批量获取消息
                messages = []
                try:
                    # 尝试在批处理间隔内获取尽可能多的消息
                    while len(messages) < self.batch_size:
                        message = await asyncio.wait_for(self.message_queue.get(), timeout=self.batch_interval)
                        messages.append(message)
                except asyncio.TimeoutError:
                    pass
                
                if messages:
                    # 批量处理消息
                    await self.batch_process_messages(messages)
                    # 标记所有消息为已处理
                    for _ in messages:
                        self.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理消息时出错: {e}")
    
    async def batch_process_messages(self, messages: List[Dict[str, Any]]):
        """批量处理消息"""
        # 按客户端分组消息
        client_messages: Dict[str, List[Dict[str, Any]]] = {}
        
        for message in messages:
            # 序列化消息中的datetime对象
            serialized_message = json.loads(json.dumps(message, cls=DateTimeEncoder))
            
            topic = serialized_message.get("topic")
            if topic and topic in self.subscriptions:
                # 消息有主题，发送给订阅的客户端
                # 使用列表副本避免字典修改问题
                for client_id in list(self.subscriptions[topic]):
                    if client_id not in client_messages:
                        client_messages[client_id] = []
                    client_messages[client_id].append(serialized_message)
            else:
                # 消息无主题，发送给所有客户端
                # 使用列表副本避免字典修改问题
                for client_id in list(self.active_connections.keys()):
                    if client_id not in client_messages:
                        client_messages[client_id] = []
                    client_messages[client_id].append(serialized_message)
        
        # 发送批量消息
        for client_id, batch_messages in client_messages.items():
            await self.send_batch_messages(client_id, batch_messages)
    
    async def send_batch_messages(self, client_id: str, batch_messages: List[Dict[str, Any]]):
        """批量发送消息给客户端"""
        if client_id in self.active_connections:
            try:
                # 检查速率限制
                if self._check_rate_limit(client_id, len(batch_messages)):
                    # 发送批量消息
                    await self.active_connections[client_id].send_json({
                        "type": "batch",
                        "messages": batch_messages
                    })
            except Exception as e:
                logger.error(f"发送批量消息到客户端 {client_id} 失败: {e}")
                # 尝试断开连接
                await self.disconnect(client_id)
    
    def _check_rate_limit(self, client_id: str, message_count: int) -> bool:
        """检查客户端消息速率限制"""
        import time
        current_time = time.time()
        
        if client_id not in self.message_counters:
            # 初始化客户端消息计数器
            self.message_counters[client_id] = [current_time, 0]
        
        timestamp, count = self.message_counters[client_id]
        
        # 检查是否在速率限制窗口内
        if current_time - timestamp < self.rate_limit_window:
            # 在窗口内，检查消息数
            if count + message_count > self.rate_limit:
                logger.warning(f"客户端 {client_id} 消息速率超过限制")
                return False
            # 更新计数
            self.message_counters[client_id][1] = count + message_count
        else:
            # 窗口外，重置计数器
            self.message_counters[client_id] = [current_time, message_count]
        
        return True
    
    async def queue_message(self, message: Dict[str, Any], topic: Optional[str] = None):
        """将消息加入队列
        
        Args:
            message: 消息内容
            topic: 主题名称
        """
        message_with_topic = message.copy()
        if topic:
            message_with_topic["topic"] = topic
        await self.message_queue.put(message_with_topic)
    
    def get_client_count(self) -> int:
        """获取当前连接数
        
        Returns:
            int: 当前连接数
        """
        return len(self.active_connections)
    
    def get_topic_count(self) -> int:
        """获取当前订阅主题数
        
        Returns:
            int: 当前订阅主题数
        """
        return len(self.subscriptions)
    
    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """获取客户端信息
        
        Args:
            client_id: 客户端ID
        
        Returns:
            Optional[Dict[str, Any]]: 客户端信息
        """
        return self.client_info.get(client_id)
    
    def update_last_ping(self, client_id: str):
        """更新客户端最后心跳时间
        
        Args:
            client_id: 客户端ID
        """
        if client_id in self.client_info:
            self.client_info[client_id]["last_ping"] = datetime.now()


# 创建全局连接管理器实例
manager = ConnectionManager()
