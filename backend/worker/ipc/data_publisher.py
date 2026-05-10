"""
数据发布器（Worker端）

从nautilus_trader引擎收集交易数据，
并通过ZMQ PUSH推送到主进程的DataCollector。
"""

import zmq.asyncio
from typing import Optional, List, Dict, Any
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)
from .protocol import Message, MessageType, serialize_message


class DataPublisher:
    """
    Worker数据发布器
    
    职责：
    1. 监听nautilus_trader的事件回调
    2. 将Position、OrderFilled等对象转换为标准格式
    3. 通过ZMQ PUSH发送到主进程
    4. 支持离线队列（连接断开时缓存消息）
    """
    
    def __init__(
        self,
        worker_id: str,
        host: str = "127.0.0.1",
        collector_port: int = 5560,
    ):
        self.worker_id = worker_id
        self.host = host
        self.collector_port = collector_port
        
        # ZMQ组件
        self._context: Optional[zmq.asyncio.Context] = None
        self._sender: Optional[zmq.asyncio.Socket] = None
        
        # 状态
        self._connected = False
        self._message_queue: List[Message] = []  # 离线队列
    
    async def connect(self) -> bool:
        """连接到主进程DataCollector"""
        try:
            self._context = zmq.asyncio.Context()
            self._sender = self._context.socket(zmq.PUSH)
            self._sender.setsockopt(zmq.LINGER, 0)
            self._sender.setsockopt(zmq.SNDHWM, 1000)  # 发送缓冲区
            self._sender.connect(f"tcp://{self.host}:{self.collector_port}")
            
            self._connected = True
            
            # 发送离线队列中的消息
            await self._flush_queue()
            
            logger.info(f"DataPublisher已连接到 DataCollector:{self.collector_port}")
            return True
            
        except Exception as e:
            logger.error(f"DataPublisher连接失败: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """断开连接"""
        self._connected = False
        
        if self._sender:
            self._sender.close()
        if self._context:
            self._context.term()
        
        logger.info("DataPublisher已断开")
    
    async def publish_trade_filled(self, fill_event):
        """
        发布成交记录
        
        Args:
            fill_event: nautilus_trader.model.events.OrderFilled
        """
        try:
            message = Message(
                msg_type=MessageType.TRADE_FILLED,
                worker_id=self.worker_id,
                payload={
                    "trade_id": str(fill_event.trade_id),
                    "client_order_id": str(fill_event.client_order_id),
                    "venue_order_id": str(fill_event.venue_order_id) if fill_event.venue_order_id else None,
                    "instrument_id": str(fill_event.instrument_id),
                    "symbol": fill_event.instrument_id.symbol,
                    "side": fill_event.order_side.name,  # BUY/SELL
                    "order_type": fill_event.order_type.name if hasattr(fill_event, 'order_type') else "MARKET",
                    "quantity": float(fill_event.last_qty),
                    "price": float(fill_event.last_px),
                    "commission": float(fill_event.commission) if fill_event.commission else 0.0,
                    "commission_currency": str(fill_event.commission.currency) if fill_event.commission else "USDT",
                    "position_id": str(fill_event.position_id) if fill_event.position_id else None,
                    "ts_event": fill_event.ts_event,
                    "ts_init": fill_event.ts_init,
                }
            )
            
            await self._send(message)
            
        except Exception as e:
            logger.error(f"发布成交记录失败: {e}")
    
    async def publish_position_update(self, position):
        """
        发布持仓更新
        
        Args:
            position: nautilus_trader.model.Position
        """
        try:
            # 计算未实现盈亏
            unrealized_pnl = 0.0
            if position.is_open and hasattr(position, 'last_event') and position.last_event:
                try:
                    from nautilus_trader.model.objects import Price
                    current_price = Price(position.last_event.last_px)
                    pnl_result = position.unrealized_pnl(current_price)
                    unrealized_pnl = float(pnl_result)
                except Exception as e:
                    logger.debug(f"计算未实现盈亏失败: {e}")
            
            message = Message(
                msg_type=MessageType.POSITION_UPDATE,
                worker_id=self.worker_id,
                payload={
                    "position_id": str(position.id),
                    "instrument_id": str(position.instrument_id),
                    "side": position.side.name,  # LONG/SHORT/FLAT
                    "signed_qty": position.signed_qty,
                    "quantity": float(position.quantity),
                    "avg_px_open": position.avg_px_open,
                    "avg_px_close": position.avg_px_close if position.avg_px_close > 0 else None,
                    "unrealized_pnl": unrealized_pnl,
                    "realized_pnl": float(position.realized_pnl) if position.realized_pnl else None,
                    "is_open": position.is_open,
                    "peak_qty": float(position.peak_qty),
                    "ts_init": position.ts_init,
                    "ts_opened": position.ts_opened if position.ts_opened > 0 else None,
                    "ts_last": position.ts_last,
                    "ts_closed": position.ts_closed if position.ts_closed > 0 else None,
                }
            )
            
            await self._send(message)
            
        except Exception as e:
            logger.error(f"发布持仓更新失败: {e}")
    
    async def publish_order_event(self, order_event):
        """
        发布订单事件
        
        Args:
            order_event: nautilus_trader.model.events.OrderEvent子类
        """
        try:
            payload = {
                "order_id": str(getattr(order_event, 'order_id', '')),
                "client_order_id": str(order_event.client_order_id),
                "venue_order_id": str(order_event.venue_order_id) if order_event.venue_order_id else None,
                "event_type": type(order_event).__name__,
                "instrument_id": str(order_event.instrument_id),
                "symbol": order_event.instrument_id.symbol,
                "side": order_event.order_side.name if hasattr(order_event, 'order_side') else None,
                "order_type": order_event.order_type.name if hasattr(order_event, 'order_type') else None,
                "ts_event": order_event.ts_event,
                "ts_init": order_event.ts_init,
            }
            
            # 成交事件特有字段
            if hasattr(order_event, 'last_qty'):
                payload.update({
                    "quantity": float(order_event.quantity) if hasattr(order_event, 'quantity') else None,
                    "price": float(order_event.price) if hasattr(order_event, 'price') else None,
                    "last_qty": float(order_event.last_qty),
                    "last_px": float(order_event.last_px),
                    "commission": float(order_event.commission) if order_event.commission else None,
                })
            
            message = Message(
                msg_type=MessageType.ORDER_EVENT,
                worker_id=self.worker_id,
                payload=payload
            )
            
            await self._send(message)
            
        except Exception as e:
            logger.error(f"发布订单事件失败: {e}")
    
    async def _send(self, message: Message):
        """发送消息（支持离线队列）"""
        if not self._connected:
            # 未连接时加入离线队列
            self._message_queue.append(message)
            if len(self._message_queue) > 1000:
                self._message_queue.pop(0)  # 防止内存溢出
            return
        
        try:
            data = serialize_message(message)
            await self._sender.send(data, flags=zmq.NOBLOCK)
        except zmq.Again:
            # 发送缓冲区满，加入队列稍后重试
            self._message_queue.append(message)
            logger.warning("发送缓冲区满，消息加入队列")
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
    
    async def _flush_queue(self):
        """刷新离线队列"""
        while self._message_queue and self._connected:
            message = self._message_queue.pop(0)
            try:
                data = serialize_message(message)
                await self._sender.send(data, flags=zmq.NOBLOCK)
            except zmq.Again:
                # 缓冲区仍满，放回队头
                self._message_queue.insert(0, message)
                break
            except Exception as e:
                logger.error(f"刷新队列失败: {e}")
                break
    
    @property
    def queue_size(self) -> int:
        """获取离线队列大小"""
        return len(self._message_queue)
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
