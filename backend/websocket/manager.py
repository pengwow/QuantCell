# WebSocket连接管理器

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Set, Optional, Any, List
import threading

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 自定义JSON编码器，处理datetime对象
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class ConnectionManager:
    """WebSocket连接管理器 - 支持跨进程广播"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """确保只有一个实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化连接管理器"""
        # 避免重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._initialized = True
        
        # 活跃连接映射: {client_id: websocket}
        self.active_connections: Dict[str, Any] = {}
        # 订阅映射: {topic: set(client_ids)}
        self.subscriptions: Dict[str, Set[str]] = {}
        # 客户端信息映射: {client_id: client_info}
        self.client_info: Dict[str, Dict[str, Any]] = {}
        # 消息队列 - 延迟初始化，在 start() 中创建
        self.message_queue: Optional[asyncio.Queue] = None
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
        
        # ZMQ 相关 - 用于跨进程通信
        self._zmq_context = None
        self._zmq_socket = None
        self._zmq_publisher = None
        self._zmq_port = 5558  # ZMQ 广播端口
        self._zmq_started = False
    
    async def start(self):
        """启动消息处理任务和 ZMQ 服务"""
        # 延迟初始化消息队列，确保在事件循环中创建
        if self.message_queue is None:
            self.message_queue = asyncio.Queue()
            logger.info("消息队列已初始化")
        
        # 启动 ZMQ 服务（用于接收子进程的消息）
        await self._start_zmq()
        
        self.processing_task = asyncio.create_task(self.process_messages())
        logger.info("WebSocket连接管理器已启动")
    
    async def _start_zmq(self):
        """启动 ZMQ 服务用于跨进程通信"""
        if self._zmq_started:
            return
        
        try:
            import zmq.asyncio
            self._zmq_context = zmq.asyncio.Context()
            
            # 创建 REP socket 接收子进程的消息（支持 REQ 客户端）
            self._zmq_socket = self._zmq_context.socket(zmq.REP)
            self._zmq_socket.bind(f"tcp://127.0.0.1:{self._zmq_port}")
            
            # 启动 ZMQ 消息接收循环
            asyncio.create_task(self._zmq_receive_loop())
            
            self._zmq_started = True
            logger.info(f"[ZMQ] 服务已启动，端口: {self._zmq_port}，使用 REQ/REP 模式")
        except Exception as e:
            logger.error(f"[ZMQ] 服务启动失败: {e}")
    
    async def process_messages(self):
        """处理消息队列中的消息"""
        logger.info("消息处理循环已启动")
        while True:
            try:
                # 从队列获取消息
                if self.message_queue:
                    message = await self.message_queue.get()
                    
                    # 处理消息
                    topic = message.get("topic")
                    if topic:
                        await self.broadcast(message, topic)
                    
                    # 标记消息为已处理
                    self.message_queue.task_done()
                else:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理消息时出错: {e}")
                await asyncio.sleep(0.1)
    
    async def queue_message(self, message: Dict[str, Any], topic: Optional[str] = None):
        """将消息加入队列

        Args:
            message: 消息内容
            topic: 主题名称
        """
        message_with_topic = message.copy()
        if topic:
            message_with_topic["topic"] = topic

        if self.message_queue:
            await self.message_queue.put(message_with_topic)
            logger.debug(f"消息加入队列: type={message.get('type')}, topic={topic}")
        else:
            logger.warning("消息队列未初始化，消息未加入队列")

    async def _zmq_receive_loop(self):
        """ZMQ 消息接收循环 - 接收子进程的消息并广播"""
        logger.info("[ZMQ] 接收循环已启动，等待消息...")
        while self._zmq_started:
            try:
                if self._zmq_socket:
                    # 使用 poll 避免阻塞，允许检查 _zmq_started
                    if await self._zmq_socket.poll(timeout=100):
                        # REP 模式接收消息
                        data = await self._zmq_socket.recv_json()
                        logger.info(f"[ZMQ] 收到原始数据: {data}")
                        message = data.get("message")
                        topic = data.get("topic")

                        if message and topic:
                            logger.info(f"[ZMQ] 收到消息: type={message.get('type')}, topic={topic}")
                            # 直接广播给 WebSocket 客户端
                            await self.broadcast(message, topic)
                            logger.info(f"[ZMQ] 消息已广播")
                            # 发送响应
                            await self._zmq_socket.send_json({"status": "ok"})
                        else:
                            logger.warning(f"[ZMQ] 收到的消息格式不正确: message={message}, topic={topic}")
                            # 发送错误响应
                            await self._zmq_socket.send_json({"status": "error", "reason": "invalid format"})
                    else:
                        # 超时，继续循环检查 _zmq_started
                        await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                # 正常取消，退出循环
                break
            except Exception as e:
                if self._zmq_started:  # 只有在运行状态下才记录错误
                    logger.error(f"[ZMQ] 接收消息错误: {e}")
                    # 尝试发送错误响应
                    try:
                        await self._zmq_socket.send_json({"status": "error", "reason": str(e)})
                    except:
                        pass
                await asyncio.sleep(0.1)
        logger.info("[ZMQ] 接收循环已停止")
    
    def update_last_ping(self, client_id: str):
        """更新客户端最后心跳时间

        Args:
            client_id: 客户端ID
        """
        if client_id in self.client_info:
            self.client_info[client_id]["last_ping"] = datetime.now()

    async def stop(self):
        """停止消息处理任务和 ZMQ 服务"""
        # 停止 ZMQ 接收循环
        self._zmq_started = False

        if self.processing_task:
            self.processing_task.cancel()
            try:
                await asyncio.wait_for(self.processing_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # 停止 ZMQ 服务
        if self._zmq_socket:
            try:
                self._zmq_socket.close()
            except Exception:
                pass
        if self._zmq_context:
            try:
                # 使用 term 的超时版本
                self._zmq_context.term()
            except Exception:
                pass

        logger.info("WebSocket连接管理器已停止")
    
    async def connect(self, websocket: Any, client_id: Optional[str] = None, topics: Optional[Set[str]] = None):
        """处理新连接
        
        Args:
            websocket: WebSocket连接对象
            client_id: 客户端ID
            topics: 初始订阅的主题列表
        
        Returns:
            str: 客户端ID
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
                    "topics": list(topics) if topics else []
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
            try:
                await self.active_connections[client_id].close()
            except:
                pass
            del self.active_connections[client_id]
            
            # 从客户端信息中移除
            if client_id in self.client_info:
                del self.client_info[client_id]
            
            # 从所有订阅中移除
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
        logger.debug(f"订阅方法被调用: client_id={client_id}, topic={topic}, manager_id={id(self)}")
        logger.debug(f"订阅前状态: subscriptions={dict((k, list(v)) for k, v in self.subscriptions.items())}")

        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
            logger.debug(f"创建新主题: {topic}")

        self.subscriptions[topic].add(client_id)

        # 更新客户端订阅信息
        if client_id in self.client_info:
            self.client_info[client_id]["topics"].add(topic)

        logger.debug(f"客户端 {client_id} 订阅了主题 {topic}")
        logger.debug(f"订阅后状态: subscriptions={dict((k, list(v)) for k, v in self.subscriptions.items())}")
        
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
        if topic in self.subscriptions and client_id in self.subscriptions[topic]:
            self.subscriptions[topic].remove(client_id)
            if not self.subscriptions[topic]:
                del self.subscriptions[topic]
            
            # 更新客户端订阅信息
            if client_id in self.client_info and topic in self.client_info[client_id]["topics"]:
                self.client_info[client_id]["topics"].remove(topic)
            
            logger.info(f"客户端 {client_id} 取消订阅了主题 {topic}")
    
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
        logger.debug(f"广播消息: type={message.get('type')}, topic={topic}")
        logger.debug(f"当前订阅状态: {dict((k, list(v)) for k, v in self.subscriptions.items())}")
        logger.debug(f"当前活跃连接: {list(self.active_connections.keys())}")
        
        if topic and topic in self.subscriptions:
            # 只广播给订阅了该主题的客户端
            client_ids = list(self.subscriptions[topic])
            if len(client_ids) > 0:
                logger.debug(f"广播给订阅了 {topic} 的客户端: {client_ids}")
                for client_id in client_ids:
                    await self.send_personal_message(message, client_id)
            else:
                logger.warning(f"主题 {topic} 没有客户端订阅，消息未发送")
        elif topic:
            # 有主题但没有客户端订阅
            logger.warning(f"主题 {topic} 没有客户端订阅，消息未发送")
        else:
            # 广播给所有客户端
            client_ids = list(self.active_connections.keys())
            logger.info(f"广播给所有客户端: {client_ids}")
            for client_id in client_ids:
                await self.send_personal_message(message, client_id)


# 创建全局连接管理器实例
manager = ConnectionManager()