"""
QuantCell WebSocket客户端

与QuantCell框架建立WebSocket连接，发送模拟数据，接收消息。
"""

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode
from loguru import logger

from ..models import (
    MarketDataMessage,
    WebSocketMessage,
    WorkerStatus,
    OrderInfo,
    PositionInfo,
    TradeSignal,
)
from ..config import QuantCellConfig


class QuantCellClient:
    """QuantCell WebSocket客户端"""
    
    def __init__(self, config: QuantCellConfig):
        self.config = config
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._authenticated = False
        self._message_handlers: Dict[str, List[Callable]] = {}
        self._tasks: List[asyncio.Task] = []
        self._reconnect_count = 0
        self._stop_event = asyncio.Event()
        
        # 统计信息
        self._messages_sent = 0
        self._messages_received = 0
        self._connection_start_time: Optional[datetime] = None
        
    @property
    def is_connected(self) -> bool:
        return self._connected and self._websocket is not None
        
    @property
    def is_authenticated(self) -> bool:
        return self._authenticated
        
    def _get_ws_url(self) -> str:
        """获取WebSocket URL"""
        protocol = "wss" if self.config.use_ssl else "ws"
        return f"{protocol}://{self.config.host}:{self.config.port}{self.config.ws_path}"
        
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        if self._connected:
            logger.warning("Already connected")
            return True
            
        url = self._get_ws_url()
        
        try:
            logger.info(f"Connecting to {url}")
            self._websocket = await asyncio.wait_for(
                websockets.connect(url),
                timeout=5.0
            )
            self._connected = True
            self._connection_start_time = datetime.now()
            
            # 启动消息接收任务
            self._tasks.append(asyncio.create_task(self._receive_loop()))
            
            # 启动心跳任务
            self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
            
            logger.info("WebSocket connected successfully")
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"Connection timeout: {url}")
            return False
        except InvalidStatusCode as e:
            logger.warning(f"Connection failed with status {e.status_code}: {url}")
            return False
        except ConnectionRefusedError:
            logger.warning(f"Connection refused: {url}. Is the QuantCell server running?")
            return False
        except OSError as e:
            logger.warning(f"Connection failed (OS error): {e}")
            return False
        except Exception as e:
            logger.warning(f"Connection failed: {e}")
            return False
            
    async def disconnect(self):
        """断开WebSocket连接"""
        self._stop_event.set()
        
        # 取消所有任务
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        
        # 关闭连接
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
            
        self._connected = False
        self._authenticated = False
        logger.info("WebSocket disconnected")
        
    async def authenticate(self) -> bool:
        """身份验证"""
        if not self._connected:
            logger.error("Not connected")
            return False
            
        if not self.config.api_key:
            logger.warning("No API key provided, skipping authentication")
            self._authenticated = True
            return True
            
        auth_message = {
            "type": "auth",
            "id": str(uuid.uuid4()),
            "timestamp": time.time() * 1000,
            "data": {
                "api_key": self.config.api_key,
                "api_secret": self.config.api_secret,
            }
        }
        
        try:
            await self._send_raw(auth_message)
            
            # 等待认证响应
            response = await asyncio.wait_for(
                self._websocket.recv(),
                timeout=5.0
            )
            
            data = json.loads(response)
            if data.get("type") == "auth_success":
                self._authenticated = True
                logger.info("Authentication successful")
                return True
            else:
                logger.error(f"Authentication failed: {data}")
                return False
                
        except asyncio.TimeoutError:
            logger.error("Authentication timeout")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
            
    async def subscribe(self, topics: List[str]) -> bool:
        """订阅主题"""
        if not self._connected:
            logger.error("Not connected")
            return False
            
        message = {
            "type": "subscribe",
            "id": str(uuid.uuid4()),
            "timestamp": time.time() * 1000,
            "data": {
                "topics": topics,
            }
        }
        
        try:
            await self._send_raw(message)
            logger.info(f"Subscribed to topics: {topics}")
            return True
        except Exception as e:
            logger.error(f"Subscribe failed: {e}")
            return False
            
    async def unsubscribe(self, topics: List[str]) -> bool:
        """取消订阅"""
        if not self._connected:
            logger.error("Not connected")
            return False
            
        message = {
            "type": "unsubscribe",
            "id": str(uuid.uuid4()),
            "timestamp": time.time() * 1000,
            "data": {
                "topics": topics,
            }
        }
        
        try:
            await self._send_raw(message)
            logger.info(f"Unsubscribed from topics: {topics}")
            return True
        except Exception as e:
            logger.error(f"Unsubscribe failed: {e}")
            return False
            
    async def send_market_data(self, message: MarketDataMessage) -> bool:
        """发送市场数据"""
        if not self._connected:
            logger.error("Not connected")
            return False
            
        ws_message = {
            "type": "market_data",
            "id": str(uuid.uuid4()),
            "timestamp": time.time() * 1000,
            "data": message.to_dict(),
        }
        
        return await self._send_raw(ws_message)
        
    async def send_control_command(self, command: str, params: Dict[str, Any] = None) -> bool:
        """发送控制命令"""
        if not self._connected:
            logger.error("Not connected")
            return False
            
        message = {
            "type": "control",
            "id": str(uuid.uuid4()),
            "timestamp": time.time() * 1000,
            "data": {
                "command": command,
                "params": params or {},
            }
        }
        
        return await self._send_raw(message)
        
    async def _send_raw(self, message: Dict[str, Any]) -> bool:
        """发送原始消息"""
        if not self._websocket:
            return False
            
        try:
            await self._websocket.send(json.dumps(message))
            self._messages_sent += 1
            return True
        except ConnectionClosed:
            logger.error("Connection closed while sending")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False
            
    async def _receive_loop(self):
        """消息接收循环"""
        while not self._stop_event.is_set():
            try:
                if not self._websocket:
                    await asyncio.sleep(0.1)
                    continue
                    
                message = await self._websocket.recv()
                self._messages_received += 1
                
                # 解析消息
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"Received invalid JSON: {message[:100]}")
                    
            except ConnectionClosed:
                logger.warning("Connection closed")
                self._connected = False
                
                # 尝试重连
                if await self._reconnect():
                    continue
                else:
                    break
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                await asyncio.sleep(0.1)
                
    async def _handle_message(self, data: Dict[str, Any]):
        """处理接收到的消息"""
        msg_type = data.get("type", "unknown")
        
        # 调用对应类型的处理器
        handlers = self._message_handlers.get(msg_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Message handler error: {e}")
                
        # 调用通用处理器
        handlers = self._message_handlers.get("*", [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Generic handler error: {e}")
                
    async def _heartbeat_loop(self):
        """心跳循环"""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=30.0  # 每30秒发送一次心跳
                )
            except asyncio.TimeoutError:
                if self._connected:
                    ping_message = {
                        "type": "ping",
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time() * 1000,
                        "data": {}
                    }
                    await self._send_raw(ping_message)
                    
    async def _reconnect(self) -> bool:
        """重新连接"""
        if self._reconnect_count >= self.config.reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return False
            
        self._reconnect_count += 1
        logger.info(f"Reconnecting... (attempt {self._reconnect_count})")
        
        await asyncio.sleep(self.config.reconnect_delay_ms / 1000.0)
        
        if await self.connect():
            if self.config.api_key:
                await self.authenticate()
            self._reconnect_count = 0
            return True
            
        return False
        
    def register_handler(self, msg_type: str, handler: Callable):
        """注册消息处理器"""
        if msg_type not in self._message_handlers:
            self._message_handlers[msg_type] = []
        self._message_handlers[msg_type].append(handler)
        
    def unregister_handler(self, msg_type: str, handler: Callable):
        """注销消息处理器"""
        if msg_type in self._message_handlers:
            if handler in self._message_handlers[msg_type]:
                self._message_handlers[msg_type].remove(handler)
                
    def get_stats(self) -> Dict[str, Any]:
        """获取连接统计"""
        duration = 0.0
        if self._connection_start_time:
            duration = (datetime.now() - self._connection_start_time).total_seconds()
            
        return {
            "connected": self._connected,
            "authenticated": self._authenticated,
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
            "connection_duration_seconds": duration,
            "reconnect_count": self._reconnect_count,
        }
