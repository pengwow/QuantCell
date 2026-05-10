"""
数据收集器

实时接收Worker推送的成交记录、持仓信息等数据，
并持久化到SQLite数据库。
"""

import asyncio
import zmq.asyncio
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)
from .protocol import Message, MessageType, serialize_message, deserialize_message
from .sqlite_manager import SQLiteManager


class DataCollector:
    """
    数据收集服务（主进程）
    
    职责：
    1. 监听ZMQ PULL端口，接收Worker数据
    2. 解析并验证消息格式
    3. 异步写入SQLite数据库
    4. 提供数据查询接口
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        data_port: int = 5560,
        db_path: str = "data/worker_data.db",
    ):
        self.host = host
        self.data_port = data_port
        self.db_path = db_path
        
        # ZMQ组件
        self._context: Optional[zmq.asyncio.Context] = None
        self._data_receiver: Optional[zmq.asyncio.Socket] = None
        
        # SQLite连接
        self._db_manager: Optional[SQLiteManager] = None
        
        # 运行状态
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # 统计指标
        self._stats = {
            "messages_received": 0,
            "trades_stored": 0,
            "positions_updated": 0,
            "order_events_stored": 0,
            "errors": 0,
            "last_message_time": None,
        }
        
        # 消息处理器注册表
        self._handlers: Dict[str, Callable] = {
            MessageType.TRADE_FILLED.value: self._handle_trade,
            MessageType.POSITION_UPDATE.value: self._handle_position,
            MessageType.ORDER_EVENT.value: self._handle_order_event,
        }
    
    async def start(self) -> bool:
        """启动数据收集服务"""
        try:
            # 初始化ZMQ
            self._context = zmq.asyncio.Context()
            self._data_receiver = self._context.socket(zmq.PULL)
            self._data_receiver.setsockopt(zmq.LINGER, 0)
            self._data_receiver.bind(f"tcp://{self.host}:{self.data_port}")
            
            # 初始化SQLite
            self._db_manager = SQLiteManager(self.db_path)
            await self._db_manager.initialize()
            
            # 启动接收循环
            self._running = True
            self._task = asyncio.create_task(self._receive_loop())
            
            logger.info(f"DataCollector已启动，监听端口 {self.data_port}")
            return True
            
        except Exception as e:
            logger.error(f"DataCollector启动失败: {e}")
            await self.stop()
            return False
    
    async def stop(self):
        """停止数据收集服务"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self._data_receiver:
            self._data_receiver.close()
        
        if self._context:
            self._context.term()
        
        if self._db_manager:
            await self._db_manager.close()
        
        logger.info("DataCollector已停止")
    
    async def _receive_loop(self):
        """数据接收主循环"""
        while self._running:
            try:
                # 非阻塞接收，超时100ms
                if await self._data_receiver.poll(timeout=100):
                    raw_data = await self._data_receiver.recv()
                    
                    # 更新统计
                    self._stats["messages_received"] += 1
                    self._stats["last_message_time"] = datetime.now()
                    
                    # 解析消息
                    message = deserialize_message(raw_data)
                    
                    # 分发到对应处理器
                    handler = self._handlers.get(message.msg_type.value)
                    if handler:
                        await handler(message)
                    else:
                        logger.warning(f"未知消息类型: {message.msg_type}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据接收错误: {e}")
                self._stats["errors"] += 1
                await asyncio.sleep(0.1)  # 错误后短暂等待
    
    async def _handle_trade(self, message: Message):
        """处理成交记录"""
        try:
            trade_data = message.payload
            
            # 构建数据库记录
            record = {
                "worker_id": int(message.worker_id.replace("worker_", "")),
                "trade_id": trade_data["trade_id"],
                "symbol": trade_data["symbol"],
                "side": trade_data["side"],
                "order_type": trade_data["order_type"],
                "quantity": trade_data["quantity"],
                "price": trade_data["price"],
                "amount": trade_data["quantity"] * trade_data["price"],
                "fee": trade_data.get("commission", 0.0),
                "client_order_id": trade_data.get("client_order_id"),
                "venue_order_id": trade_data.get("venue_order_id"),
                "position_id": trade_data.get("position_id"),
                "ts_event": trade_data.get("ts_event"),
                "ts_init": trade_data.get("ts_init"),
                "created_at": datetime.now(),
            }
            
            # 异步写入SQLite
            await self._db_manager.insert_trade(record)
            self._stats["trades_stored"] += 1
            
            logger.debug(f"成交记录已存储: {trade_data['trade_id']}")
            
        except Exception as e:
            logger.error(f"处理成交记录失败: {e}")
            self._stats["errors"] += 1
    
    async def _handle_position(self, message: Message):
        """处理持仓更新"""
        try:
            pos_data = message.payload
            
            # 构建持仓快照
            snapshot = {
                "worker_id": int(message.worker_id.replace("worker_", "")),
                "position_id": pos_data["position_id"],
                "instrument_id": pos_data["instrument_id"],
                "symbol": pos_data["instrument_id"].split(".")[0] if "." in pos_data.get("instrument_id", "") else pos_data.get("instrument_id", ""),
                "side": pos_data["side"],
                "signed_qty": pos_data["signed_qty"],
                "quantity": pos_data["quantity"],
                "avg_px_open": pos_data["avg_px_open"],
                "unrealized_pnl": pos_data.get("unrealized_pnl", 0.0),
                "is_open": pos_data.get("is_open", True),
                "ts_last": pos_data.get("ts_last"),
                "snapshot_time": datetime.now(),
            }
            
            # 写入SQLite（upsert）
            await self._db_manager.upsert_position(snapshot)
            self._stats["positions_updated"] += 1
            
            logger.debug(f"持仓快照已更新: {pos_data['position_id']}")
            
        except Exception as e:
            logger.error(f"处理持仓更新失败: {e}")
            self._stats["errors"] += 1
    
    async def _handle_order_event(self, message: Message):
        """处理订单事件"""
        try:
            event_data = message.payload
            
            record = {
                "worker_id": int(message.worker_id.replace("worker_", "")),
                "order_id": event_data.get("order_id", ""),
                "client_order_id": event_data.get("client_order_id"),
                "venue_order_id": event_data.get("venue_order_id"),
                "event_type": event_data["event_type"],
                "instrument_id": event_data["instrument_id"],
                "symbol": event_data["symbol"],
                "side": event_data["side"],
                "order_type": event_data["order_type"],
                "quantity": event_data.get("quantity"),
                "price": event_data.get("price"),
                "last_qty": event_data.get("last_qty"),
                "last_px": event_data.get("last_px"),
                "commission": event_data.get("commission"),
                "ts_event": event_data.get("ts_event"),
                "ts_init": event_data.get("ts_init"),
            }
            
            await self._db_manager.insert_order_event(record)
            self._stats["order_events_stored"] += 1
            
        except Exception as e:
            logger.error(f"处理订单事件失败: {e}")
            self._stats["errors"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    @property
    def db_manager(self) -> Optional[SQLiteManager]:
        """获取SQLite管理器实例（用于外部查询）"""
        return self._db_manager
