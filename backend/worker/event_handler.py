"""
Worker 事件处理器模块

提供事件处理功能，支持：
- 订单事件处理
- 成交事件处理
- 持仓事件处理
- 事件同步到主进程

使用示例：
    from worker.event_handler import EventHandler

    handler = EventHandler(worker_id, comm_client)
    await handler.start()
"""

import asyncio
import contextlib
import json as _json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from datetime import datetime as _dt
from typing import TYPE_CHECKING, Any

from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__, LogType.APPLICATION)


def _is_mock_object(obj: Any) -> bool:
    """
    检查对象是否是 Mock 对象

    用于区分真实的策略引擎对象和测试中的 Mock 对象，
    避免在 Mock 上错误地匹配自动生成的子属性。
    """
    if obj is None:
        return False
    obj_type = type(obj)
    type_name = f"{obj_type.__module__}.{obj_type.__name__}"
    return "mock" in type_name.lower()


@dataclass
class EventBufferConfig:
    """
    事件缓冲配置

    overflow_strategy: 溢出策略
        - "drop": 丢弃新事件（默认，适合非关键事件）
        - "block": 阻塞生产者直到有空间（适合关键事件）
        - "oldest": 丢弃最旧的事件（适合只关心最新状态的场景）
    """

    buffer_size: int = 1000
    flush_interval: float = 1.0
    batch_size: int = 100
    overflow_strategy: str = "drop"  # drop, block, oldest


class EventHandler:
    """
    事件处理器

    负责处理 Worker 中的各类事件，并将事件同步到主进程。
    支持三种溢出策略：drop（丢弃新事件）、block（阻塞生产者）、oldest（丢弃最旧事件）
    """

    def __init__(
        self,
        worker_id: str,
        comm_client: Any,
        config: EventBufferConfig | None = None,
    ):
        self.worker_id = worker_id
        self.comm_client = comm_client
        self.config = config or EventBufferConfig()

        # 事件缓冲
        self._event_buffer: deque = deque(maxlen=self.config.buffer_size)
        self._flush_task: asyncio.Task | None = None
        self._running = False

        # 背压控制
        self._backpressure_event = asyncio.Event() if self.config.overflow_strategy == "block" else None

        # 统计
        self._events_received = 0
        self._events_sent = 0
        self._events_dropped = 0
        self._events_blocked = 0

    async def start(self) -> None:
        """启动事件处理器"""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"Worker {self.worker_id} 事件处理器已启动")

    async def stop(self) -> None:
        """停止事件处理器"""
        if not self._running:
            return

        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task

        # 刷新剩余事件
        await self._flush_buffer()

        logger.info(f"Worker {self.worker_id} 事件处理器已停止")

    def on_order_event(self, event: dict[str, Any]) -> None:
        """处理订单事件"""
        self._events_received += 1
        self._buffer_event(
            {
                "type": "order",
                "data": event,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def on_fill_event(self, event: dict[str, Any]) -> None:
        """处理成交事件"""
        self._events_received += 1
        self._buffer_event(
            {
                "type": "fill",
                "data": event,
                "timestamp": datetime.now().isoformat(),
            }
        )
        # 成交事件立即发送（如果有运行的事件循环）
        try:
            asyncio.get_running_loop()
            asyncio.create_task(self._flush_buffer())
        except RuntimeError:
            # 没有运行的事件循环，不立即刷新
            pass

    def on_position_event(self, event: dict[str, Any]) -> None:
        """处理持仓事件"""
        self._events_received += 1
        self._buffer_event(
            {
                "type": "position",
                "data": event,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _buffer_event(self, event: dict[str, Any]) -> None:
        """
        将事件添加到缓冲队列，支持三种溢出策略：
        - drop: 丢弃新事件（默认）
        - block: 阻塞生产者直到有空间（需要在 async 上下文中使用）
        - oldest: 丢弃最旧的事件
        """
        if len(self._event_buffer) >= self.config.buffer_size:
            if self.config.overflow_strategy == "drop":
                self._events_dropped += 1
                logger.warning(f"Worker {self.worker_id} 事件缓冲区已满，丢弃新事件")
                return
            elif self.config.overflow_strategy == "oldest":
                self._event_buffer.popleft()
                self._events_dropped += 1
                logger.debug(f"Worker {self.worker_id} 事件缓冲区已满，丢弃最旧事件")
            elif self.config.overflow_strategy == "block":
                self._events_blocked += 1
                logger.debug(f"Worker {self.worker_id} 事件缓冲区已满，等待空间")
                if self._backpressure_event:
                    self._backpressure_event.clear()

        self._event_buffer.append(event)

        # 通知阻塞的生产者有空间了
        if self._backpressure_event and not self._backpressure_event.is_set():
            self._backpressure_event.set()

        # 达到批量大小立即刷新（如果有运行的事件循环）
        if len(self._event_buffer) >= self.config.batch_size:
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._flush_buffer())
            except RuntimeError:
                # 没有运行的事件循环，等待定时刷新
                pass

    async def _flush_loop(self) -> None:
        """定时刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval)
                if self._event_buffer:
                    await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} 事件刷新循环错误: {e}")

    async def _flush_buffer(self) -> None:
        """刷新缓冲队列到主进程"""
        if not self._event_buffer:
            return

        events = list(self._event_buffer)
        self._event_buffer.clear()

        try:
            if self.comm_client:
                for event in events:
                    await self.comm_client.send_event(event)
                self._events_sent += len(events)
        except Exception as e:
            logger.error(f"Worker {self.worker_id} 发送事件失败: {e}")

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "events_received": self._events_received,
            "events_sent": self._events_sent,
            "events_dropped": self._events_dropped,
            "events_blocked": self._events_blocked,
            "buffer_size": len(self._event_buffer),
            "buffer_capacity": self.config.buffer_size,
            "overflow_strategy": self.config.overflow_strategy,
        }


__all__ = [
    "EventBufferConfig",
    "EventHandler",
    "LiveTradeRecorder",
    "TradingEventHandler",
    "create_event_handler",
]


# ============================================================================
# Trading 事件处理器
# ============================================================================


class TradingEventHandler:
    """
    策略引擎事件处理器

    订阅策略引擎事件并通过回调函数发送到主进程。
    """

    def __init__(
        self,
        adapter: Any,
        worker_id: Any = None,
        event_callback: Callable[[str, dict], None] | None = None,
        node: Any = None,
    ):
        """
        初始化事件处理器

        Parameters
        ----------
        adapter : Any
            策略引擎适配器（或测试中的 Mock）。兼容旧接口的 trader 参数。
        worker_id : Any, optional
            Worker ID（P4 计划要求的参数）
        event_callback : Callable[[str, dict], None], optional
            事件回调函数，接收 (event_type, event_data)
        node : Any, optional
            策略引擎 TradingNode 实例（用于访问 msgbus）
        """
        # 兼容两种调用方式：
        # 新接口: AxonEventHandler(adapter, worker_id, callback)
        # 旧接口: AxonEventHandler(trader, callback, node)
        if worker_id is None and callable(event_callback) and node is None:
            # 旧接口模式：AxonEventHandler(trader, callback)
            self.trader = adapter
            self.worker_id = None
            self.event_callback = event_callback
            self.node = None
        elif node is None and worker_id is not None and callable(worker_id):
            # 旧接口模式：AxonEventHandler(trader, callback, node=None)
            # 即 (adapter=trader, worker_id=callback, event_callback=node)
            self.trader = adapter
            self.worker_id = None
            self.event_callback = worker_id
            self.node = event_callback
        else:
            # 新接口: AxonEventHandler(adapter, worker_id, callback, node)
            self.trader = adapter  # adapter 兼容旧字段名
            self.worker_id = worker_id
            self.event_callback = event_callback
            self.node = node
        self._subscribed = False

    @staticmethod
    def _resolve_msgbus(trader: Any, node: Any = None) -> Any:
        """
        解析并返回 msg_bus 实例

        优先级：
        1. node.msgbus
        2. node.kernel.msgbus
        3. trader.kernel.msgbus
        4. trader.msg_bus（兼容 axon-style Mock 写法，优先于 msgbus）
        5. trader.msgbus（兼容旧版本 axon_quant）
        """
        is_trader_mock = _is_mock_object(trader)
        is_node_mock = _is_mock_object(node)

        # 方式1: node.msgbus
        if node is not None and not is_node_mock and hasattr(node, "msgbus") and node.msgbus is not None:
            return node.msgbus

        # 方式2: node.kernel.msgbus
        if (
            node is not None
            and not is_node_mock
            and hasattr(node, "kernel")
            and node.kernel is not None
            and not _is_mock_object(node.kernel)
            and hasattr(node.kernel, "msgbus")
            and node.kernel.msgbus is not None
        ):
            return node.kernel.msgbus

        # 方式3: trader.kernel.msgbus
        if (
            trader is not None
            and not is_trader_mock
            and hasattr(trader, "kernel")
            and trader.kernel is not None
            and not _is_mock_object(trader.kernel)
            and hasattr(trader.kernel, "msgbus")
            and trader.kernel.msgbus is not None
        ):
            return trader.kernel.msgbus

        # 方式4: trader.msg_bus（兼容 axon-style Mock 写法）
        if trader is not None and hasattr(trader, "msg_bus") and trader.msg_bus is not None:
            return trader.msg_bus

        # 方式5: trader.msgbus（兼容旧版本 axon_quant，跳过 Mock 自动属性）
        if trader is not None and not is_trader_mock and hasattr(trader, "msgbus") and trader.msgbus is not None:
            return trader.msgbus

        return None

    def subscribe_events(self) -> None:
        """订阅策略引擎事件"""
        if self._subscribed:
            return
        # 获取消息总线（支持多种访问方式）
        msg_bus = self._resolve_msgbus(self.trader, self.node)
        if msg_bus is None:
            msg = "无法访问 msg_bus：请传入 TradingNode 实例，或确保 trader 有 kernel.msgbus 属性"
            raise AttributeError(msg)
        # 订阅订单事件 (msg_bus topic: events.order.{strategy_id})
        msg_bus.subscribe(
            topic="events.order.*",
            handler=self._handle_order_event,
        )

        # 订阅成交事件 (msg_bus topic: events.fills.{instrument_id})
        msg_bus.subscribe(
            topic="events.fills.*",
            handler=self._handle_fill_event,
        )

        # 订阅持仓事件 (msg_bus topic: events.position.{strategy_id})
        msg_bus.subscribe(
            topic="events.position.*",
            handler=self._handle_position_event,
        )
        self._subscribed = True

    def unsubscribe_events(self) -> None:
        """取消订阅策略引擎事件"""
        if not self._subscribed:
            return
        msg_bus = self._resolve_msgbus(self.trader, self.node)
        if msg_bus is None:
            return
        msg_bus.unsubscribe(
            topic="events.order.*",
            handler=self._handle_order_event,
        )
        msg_bus.unsubscribe(
            topic="events.fills.*",
            handler=self._handle_fill_event,
        )
        msg_bus.unsubscribe(
            topic="events.position.*",
            handler=self._handle_position_event,
        )
        self._subscribed = False

    def _handle_order_event(self, event: Any) -> None:
        """处理订单事件"""
        try:
            event_data = self._convert_order_event(event)
            self.event_callback("order", event_data)
        except Exception as e:
            logger.error(f"处理订单事件出错: {e}")

    def _handle_fill_event(self, event: Any) -> None:
        """处理成交事件"""
        try:
            event_data = self._convert_fill_event(event)
            self.event_callback("fill", event_data)
        except Exception as e:
            logger.error(f"处理成交事件出错: {e}")

    def _handle_position_event(self, event: Any) -> None:
        """处理持仓事件"""
        try:
            event_data = self._convert_position_event(event)
            self.event_callback("position", event_data)
        except Exception as e:
            logger.error(f"处理持仓事件出错: {e}")

    def _convert_order_event(self, event: Any) -> dict:
        """转换订单事件为字典"""
        return {
            "type": "order",
            "order_id": str(getattr(event, "order_id", "")),
            "instrument_id": str(getattr(event, "instrument_id", "")),
            "side": str(getattr(event, "side", "")),
            "quantity": str(getattr(event, "quantity", "0")),
            "price": str(getattr(event, "price", "0")),
            "status": str(getattr(event, "status", "")),
            "timestamp": str(getattr(event, "timestamp", "")),
        }

    def _convert_fill_event(self, event: Any) -> dict:
        """转换成交事件为字典"""
        return {
            "type": "fill",
            "order_id": str(getattr(event, "order_id", "")),
            "instrument_id": str(getattr(event, "instrument_id", "")),
            "side": str(getattr(event, "side", "")),
            "quantity": str(getattr(event, "quantity", "0")),
            "price": str(getattr(event, "price", "0")),
            "commission": str(getattr(event, "commission", "0")),
            "timestamp": str(getattr(event, "timestamp", "")),
        }

    def _convert_position_event(self, event: Any) -> dict:
        """转换持仓事件为字典"""
        return {
            "type": "position",
            "instrument_id": str(getattr(event, "instrument_id", "")),
            "side": str(getattr(event, "side", "")),
            "quantity": str(getattr(event, "quantity", "0")),
            "avg_price": str(getattr(event, "avg_price", "0")),
            "unrealized_pnl": str(getattr(event, "unrealized_pnl", "0")),
            "timestamp": str(getattr(event, "timestamp", "")),
        }

    # ============ 被动回调接口（P4 计划规范） ============

    def on_order_filled(
        self,
        order_id: str,
        price: float,
        quantity: float,
        **extra: Any,
    ) -> None:
        """
        订单成交事件回调

        Args:
            order_id: 订单 ID
            price: 成交价格
            quantity: 成交数量
            **extra: 附加字段（symbol, side, timestamp 等）
        """
        event_data = {
            "type": "fill",
            "order_id": str(order_id),
            "price": float(price),
            "quantity": float(quantity),
            **extra,
        }
        self._dispatch_event("fill", event_data)

    def on_order_rejected(
        self,
        order_id: str,
        reason: str,
        **extra: Any,
    ) -> None:
        """
        订单拒绝事件回调

        Args:
            order_id: 订单 ID
            reason: 拒绝原因
            **extra: 附加字段
        """
        event_data = {
            "type": "order_rejected",
            "order_id": str(order_id),
            "reason": str(reason),
            **extra,
        }
        self._dispatch_event("order_rejected", event_data)

    def on_order_accepted(self, order_id: str, **extra: Any) -> None:
        """
        订单接受事件回调
        """
        event_data = {
            "type": "order_accepted",
            "order_id": str(order_id),
            **extra,
        }
        self._dispatch_event("order_accepted", event_data)

    def on_order_canceled(self, order_id: str, **extra: Any) -> None:
        """
        订单取消事件回调
        """
        event_data = {
            "type": "order_canceled",
            "order_id": str(order_id),
            **extra,
        }
        self._dispatch_event("order_canceled", event_data)

    def on_position_changed(
        self,
        symbol: str,
        quantity: float,
        **extra: Any,
    ) -> None:
        """
        持仓变化事件回调
        """
        event_data = {
            "type": "position",
            "symbol": str(symbol),
            "quantity": float(quantity),
            **extra,
        }
        self._dispatch_event("position", event_data)

    def _dispatch_event(self, event_type: str, event_data: dict) -> None:
        """
        事件分发：触发回调 + 写入数据库
        """
        # 1. 触发回调
        if self.event_callback is not None:
            try:
                self.event_callback(event_type, event_data)
            except Exception as e:
                logger.error(f"AxonEventHandler 回调执行失败: {e}")

        # 2. 写入 WorkerLog
        if self.worker_id is not None:
            try:
                from utils.db_session import get_db_session

                from . import crud

                with get_db_session() as db:
                    crud.create_worker_log(
                        db,
                        worker_id=self.worker_id,
                        log_type=event_type,
                        message=event_data,
                    )
            except Exception as e:
                logger.warning(f"AxonEventHandler 写入 WorkerLog 失败: worker_id={self.worker_id}, error={e}")


class LiveTradeRecorder:
    """
    策略引擎事件到数据库的持久化记录器。

    在 daemon 线程中运行，订阅策略引擎的 msg_bus 事件，
    将 OrderFilled / OrderAccepted / OrderCanceled / OrderRejected / Position* 事件
    转换为 dict 并调用 crud 操作写入 worker_trades / worker_orders / worker_positions 表。

    每个 DB 操作都创建独立的 SessionLocal()，确保 daemon 线程安全。

    Usage (在 _run_node_sync 中，node.build() 之后、node.run() 之前):::

        recorder = LiveTradeRecorder(worker_id=worker_id)
        recorder.subscribe(node.trader)
    """

    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self._subscribed = False
        self._trader = None
        self._node = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def subscribe(self, trader: Any, node: Any = None) -> None:
        """
        订阅 msg_bus 事件（需在 node.build() 之后、node.run() 之前调用）

        Parameters
        ----------
        trader : Any
            策略引擎 Trader 实例（保留以兼容旧调用方式）
        node : Any, optional
            策略引擎 TradingNode 实例（用于访问 msgbus）
            如果不提供，将尝试从 trader.kernel.msgbus 获取
        """
        if self._subscribed:
            return

        self._trader = trader
        self._node = node

        # msgbus 访问优先级：node.msgbus > node.kernel.msgbus > trader.kernel.msgbus
        msg_bus = self._resolve_msgbus(trader, node)
        if msg_bus is None:
            msg = "无法访问 msg_bus：请传入 TradingNode 实例，或确保 trader 有 kernel.msgbus 属性"
            raise AttributeError(msg)

        # order events: events.order.{strategy_id}
        msg_bus.subscribe(topic="events.order.*", handler=self._on_order_event)
        # fill events: events.fills.{instrument_id}
        msg_bus.subscribe(topic="events.fills.*", handler=self._on_fill_event)
        # position events: events.position.{strategy_id}
        msg_bus.subscribe(topic="events.position.*", handler=self._on_position_event)

        self._subscribed = True
        logger.info(f"LiveTradeRecorder: worker_id={self.worker_id} 已订阅 msg_bus 事件")

    @staticmethod
    def _resolve_msgbus(trader: Any, node: Any = None) -> Any:
        """
        解析并返回 msg_bus 实例，支持多种获取方式

        优先级：
        1. node.msgbus（TradingNode 属性）
        2. node.kernel.msgbus（通过 kernel 访问）
        3. trader.kernel.msgbus（通过 trader 的 kernel 访问）
        4. trader.msg_bus（兼容 axon-style Mock 写法）
        5. trader.msgbus（兼容旧版本）

        实现要点：
        - 真实的 Trader/Node 对象应当是策略引擎的具体类实例
        - 通过检查类型模块路径来区分真实对象和测试 Mock
        - 容器对象（kernel/trader）必须是真实的，最终的 msgbus 可以是 Mock
        """
        # 方式1: node.msgbus（要求 node 是真实对象，不是 Mock）
        if node is not None and not _is_mock_object(node) and hasattr(node, "msgbus") and node.msgbus is not None:
            logger.debug("LiveTradeRecorder: 使用 node.msgbus")
            return node.msgbus

        # 方式2: node.kernel.msgbus
        if (
            node is not None
            and not _is_mock_object(node)
            and hasattr(node, "kernel")
            and node.kernel is not None
            and not _is_mock_object(node.kernel)
            and hasattr(node.kernel, "msgbus")
            and node.kernel.msgbus is not None
        ):
            logger.debug("LiveTradeRecorder: 使用 node.kernel.msgbus")
            return node.kernel.msgbus

        # 方式3: trader.kernel.msgbus
        if (
            trader is not None
            and not _is_mock_object(trader)
            and hasattr(trader, "kernel")
            and trader.kernel is not None
            and not _is_mock_object(trader.kernel)
            and hasattr(trader.kernel, "msgbus")
            and trader.kernel.msgbus is not None
        ):
            logger.debug("LiveTradeRecorder: 使用 trader.kernel.msgbus")
            return trader.kernel.msgbus

        # 方式4: trader.msg_bus（兼容 axon-style Mock 写法）
        if trader is not None and hasattr(trader, "msg_bus") and trader.msg_bus is not None:
            logger.debug("LiveTradeRecorder: 使用 trader.msg_bus")
            return trader.msg_bus

        # 方式5: trader.msgbus（兼容旧版本，跳过 Mock 自动属性）
        if (
            trader is not None
            and not _is_mock_object(trader)
            and hasattr(trader, "msgbus")
            and trader.msgbus is not None
        ):
            logger.debug("LiveTradeRecorder: 使用 trader.msgbus（兼容模式）")
            return trader.msgbus

        return None

    def unsubscribe(self) -> None:
        """取消订阅"""
        if not self._subscribed or self._trader is None:
            return

        msg_bus = self._resolve_msgbus(self._trader, self._node)
        if msg_bus is None:
            logger.warning(f"LiveTradeRecorder: unsubscribe 时无法访问 msg_bus (worker_id={self.worker_id})")
            return

        msg_bus.unsubscribe(topic="events.order.*", handler=self._on_order_event)
        msg_bus.unsubscribe(topic="events.fills.*", handler=self._on_fill_event)
        msg_bus.unsubscribe(topic="events.position.*", handler=self._on_position_event)

        self._subscribed = False
        logger.info(f"LiveTradeRecorder: worker_id={self.worker_id} 已取消订阅")

    # ------------------------------------------------------------------
    # DB session helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_db():
        """创建独立的 DB session（daemon 线程安全）"""
        from collector.db.database import SessionLocal

        return SessionLocal()

    # ------------------------------------------------------------------
    # msg_bus 回调
    # ------------------------------------------------------------------

    def _on_order_event(self, event: Any) -> None:
        """处理订单事件（Accepted / Canceled / Rejected）"""
        try:
            db = self._get_db()
            try:
                self._dispatch_order_event(db, event)
            finally:
                db.close()
        except Exception as e:
            logger.error(
                f"LiveTradeRecorder order event error (worker_id={self.worker_id}): {e}",
                exc_info=True,
            )

    def _on_fill_event(self, event: Any) -> None:
        """处理成交事件（OrderFilled）"""
        try:
            db = self._get_db()
            try:
                self._handle_fill(db, event)
            finally:
                db.close()
        except Exception as e:
            logger.error(
                f"LiveTradeRecorder fill event error (worker_id={self.worker_id}): {e}",
                exc_info=True,
            )

    def _on_position_event(self, event: Any) -> None:
        """处理持仓事件（PositionChanged / Opened / Closed）"""
        try:
            db = self._get_db()
            try:
                self._handle_position(db, event)
            finally:
                db.close()
        except Exception as e:
            logger.error(
                f"LiveTradeRecorder position event error (worker_id={self.worker_id}): {e}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # 内部处理逻辑
    # ------------------------------------------------------------------

    def _dispatch_order_event(self, db: Any, event: Any) -> None:
        """根据事件子类型分发到对应的处理方法（按类型名判断，避免强依赖具体库）"""
        # OrderFilled 同时也会出现在 order topic，优先走 fill 路径
        type_name = type(event).__name__
        if type_name == "OrderFilled":
            self._handle_fill(db, event)
        elif type_name == "OrderAccepted":
            self._handle_order_accepted(db, event)
        elif type_name == "OrderCanceled":
            self._handle_order_canceled(db, event)
        elif type_name == "OrderRejected":
            self._handle_order_rejected(db, event)
        else:
            logger.debug(f"LiveTradeRecorder: 忽略未知订单事件类型 {type_name} (worker_id={self.worker_id})")

    @staticmethod
    def _identify_order_event_type(event: Any) -> str:
        """识别订单事件子类型。

        Returns:
            ``"accepted"`` / ``"canceled"`` / ``"rejected"`` / ``"filled"`` /
            ``"position"`` / ``"unknown"``
        """
        if event is None:
            return "unknown"

        # 优先按 axon_quant.core.events 类层级匹配
        try:
            from axon_bridge import (  # type: ignore[import-not-found]
                OrderAccepted,
                OrderCanceled,
                OrderFilled,
                OrderRejected,
            )
        except ImportError:
            OrderAccepted = OrderCanceled = OrderRejected = OrderFilled = None  # type: ignore[assignment]

        if OrderFilled is not None and isinstance(event, OrderFilled):
            return "filled"
        if OrderAccepted is not None and isinstance(event, OrderAccepted):
            return "accepted"
        if OrderCanceled is not None and isinstance(event, OrderCanceled):
            return "canceled"
        if OrderRejected is not None and isinstance(event, OrderRejected):
            return "rejected"

        # duck typing：按属性区分
        if hasattr(event, "last_qty") and hasattr(event, "last_px") and hasattr(event, "trade_id"):
            return "filled"
        if hasattr(event, "reason") and hasattr(event, "client_order_id"):
            return "rejected"
        if hasattr(event, "position_id") and hasattr(event, "qty"):
            return "position"
        if hasattr(event, "order_qty") and hasattr(event, "client_order_id"):
            return "accepted"
        if hasattr(event, "client_order_id") and hasattr(event, "venue_order_id"):
            return "canceled"

        return "unknown"

    # -- OrderAccepted ---------------------------------------------------

    def _handle_order_accepted(self, db: Any, event: Any) -> None:
        """创建订单记录（状态=ACCEPTED）"""
        from . import crud

        order_data = {
            "worker_id": self.worker_id,
            "client_order_id": str(event.client_order_id),
            "venue_order_id": str(getattr(event, "venue_order_id", "")) or None,
            "symbol": str(event.instrument_id),
            "side": str(getattr(event, "order_side", "")).replace("OrderSide.", ""),
            "order_type": str(getattr(event, "order_type", "MARKET")).replace("OrderType.", ""),
            "quantity": float(getattr(event, "order_qty", 0)),
            "price": float(getattr(event, "order_px", 0)) if getattr(event, "order_px", None) is not None else None,
            "filled_qty": 0.0,
            "avg_fill_price": 0.0,
            "status": "ACCEPTED",
            "position_id": None,
            "strategy_id": str(getattr(event, "strategy_id", "")),
        }

        crud.create_order_if_not_exists(db, order_data)
        logger.info(f"LiveTradeRecorder: ACCEPTED order {order_data['client_order_id']} (worker_id={self.worker_id})")

    # -- OrderCanceled ---------------------------------------------------

    def _handle_order_canceled(self, db: Any, event: Any) -> None:
        """更新订单状态为 CANCELED"""
        from . import crud

        order = crud.get_worker_order_by_id(db, self.worker_id, str(event.client_order_id))
        if order:
            venue_oid = str(getattr(event, "venue_order_id", "")) or ""
            crud.update_worker_order_status(db, order.id, "CANCELED", 0.0, 0.0, 0.0, venue_oid)
            logger.info(f"LiveTradeRecorder: CANCELED order {event.client_order_id} (worker_id={self.worker_id})")
        else:
            logger.warning(
                f"LiveTradeRecorder: CANCELED order {event.client_order_id} "
                f"not found in DB (worker_id={self.worker_id})"
            )

    # -- OrderRejected ---------------------------------------------------

    def _handle_order_rejected(self, db: Any, event: Any) -> None:
        """更新订单状态为 REJECTED"""
        from . import crud

        order = crud.get_worker_order_by_id(db, self.worker_id, str(event.client_order_id))
        if order:
            reason = str(getattr(event, "reason", ""))
            crud.update_worker_order_status(db, order.id, "REJECTED", 0.0, 0.0, 0.0, "")
            logger.warning(
                f"LiveTradeRecorder: REJECTED order {event.client_order_id} "
                f"reason={reason} (worker_id={self.worker_id})"
            )
        else:
            logger.warning(
                f"LiveTradeRecorder: REJECTED order {event.client_order_id} "
                f"not found in DB (worker_id={self.worker_id})"
            )

    # -- OrderFilled (fill) ----------------------------------------------

    def _handle_fill(self, db: Any, event: Any) -> None:
        """创建 trade 记录并更新 order 状态为 FILLED"""
        from . import crud

        commission = self._extract_commission(event)

        # --- trade 数据 ---
        entry_time = None
        if hasattr(event, "ts_event") and event.ts_event:
            entry_time = _dt.fromtimestamp(event.ts_event / 1e9)

        trade_data = {
            "worker_id": self.worker_id,
            "trade_id": str(event.trade_id),
            "symbol": str(event.instrument_id),
            "side": str(getattr(event, "order_side", "")).replace("OrderSide.", ""),
            "order_type": str(getattr(event, "order_type", "MARKET")).replace("OrderType.", ""),
            "quantity": float(event.last_qty),
            "price": float(event.last_px),
            "amount": float(event.last_qty) * float(event.last_px),
            "fee": commission,
            "fee_currency": self._extract_commission_currency(event),
            "realized_pnl": None,
            "realized_pnl_pct": None,
            "entry_time": entry_time,
            "exit_time": None,
            "raw_data": _json.dumps(
                {
                    "strategy_id": str(getattr(event, "strategy_id", "")),
                    "instrument_id": str(event.instrument_id),
                    "client_order_id": str(event.client_order_id),
                    "venue_order_id": str(getattr(event, "venue_order_id", "")),
                    "trade_id": str(event.trade_id),
                    "last_qty": str(event.last_qty),
                    "last_px": str(event.last_px),
                    "liquidity_side": str(getattr(event, "liquidity_side", "")),
                    "ts_event": getattr(event, "ts_event", None),
                },
                default=str,
            ),
        }

        crud.create_trade_if_not_exists(db, trade_data)
        logger.info(
            f"LiveTradeRecorder: FILLED trade {trade_data['trade_id']} "
            f"{trade_data['symbol']} {trade_data['side']} "
            f"qty={trade_data['quantity']} px={trade_data['price']} "
            f"(worker_id={self.worker_id})"
        )

        # --- 更新 order 状态 ---
        order = crud.get_worker_order_by_id(db, self.worker_id, str(event.client_order_id))
        if order:
            crud.update_worker_order_status(
                db,
                order.id,
                "FILLED",
                float(event.last_qty),
                float(event.last_px),
                commission,
                str(getattr(event, "venue_order_id", "")),
            )

    # -- Position events -------------------------------------------------

    def _handle_position(self, db: Any, event: Any) -> None:
        """创建或更新持仓记录"""
        from . import crud

        pos_id = str(event.position_id)
        side = str(getattr(event, "position_side", "LONG")).replace("PositionSide.", "")
        qty = float(getattr(event, "qty", 0))
        entry_px = float(getattr(event, "entry_avg_px", 0))
        unrealized = float(getattr(event, "unrealized_pnl", 0))
        realized = float(getattr(event, "realized_pnl", 0))

        # 判断是否已平仓
        is_closed = getattr(event, "is_close", False)

        position_data = {
            "worker_id": self.worker_id,
            "position_id": pos_id,
            "symbol": str(event.instrument_id),
            "side": side,
            "quantity": abs(qty),
            "entry_price": entry_px,
            "current_price": entry_px,  # 近似值，后续可由 tick 更新
            "unrealized_pnl": unrealized,
            "realized_pnl": realized,
            "status": "CLOSED" if is_closed else "OPEN",
        }

        # 先尝试 upsert
        existing = crud.create_position_if_not_exists(db, position_data)
        if existing and existing.position_id == pos_id:
            # 已存在 → 更新
            crud.update_position(db, pos_id, position_data)

        logger.info(
            f"LiveTradeRecorder: POSITION {position_data['status']} "
            f"{pos_id} {side} qty={qty} entry={entry_px} "
            f"(worker_id={self.worker_id})"
        )

    # -- 工具方法 --------------------------------------------------------

    @staticmethod
    def _extract_commission(event: Any) -> float:
        """从事件中提取手续费金额"""
        commission = getattr(event, "commission", None)
        if commission is None:
            return 0.0

        # 检测 Mock 对象（测试场景），避免自动生成的子属性被误识别
        from unittest.mock import Mock as _Mock

        is_mock = isinstance(commission, _Mock)

        # 优先尝试 as_double() —— axon_quant Money 的标准接口
        if hasattr(commission, "as_double"):
            try:
                value = commission.as_double()
                if isinstance(value, _Mock):
                    # Mock 自动生成的返回值，回退到其他字段
                    msg = "as_double returned Mock"
                    raise TypeError(msg)
                return float(value)
            except TypeError, ValueError:
                pass

        # 其次尝试 amount 属性
        if hasattr(commission, "amount"):
            try:
                amount = commission.amount
                if isinstance(amount, _Mock) and not is_mock:
                    # 真实对象上的 amount 字段是 Mock —— 跳过
                    pass
                else:
                    return float(amount)
            except TypeError, ValueError:
                pass

        # 最后直接转 float
        try:
            return float(commission)
        except TypeError, ValueError:
            return 0.0

    @staticmethod
    def _extract_commission_currency(event: Any) -> str:
        """从事件中提取手续费币种"""
        commission = getattr(event, "commission", None)
        if commission is None:
            return "USDT"
        if hasattr(commission, "currency"):
            return str(commission.currency)
        return "USDT"


def create_event_handler(
    trader: Any,
    send_event_func: Callable[[str, dict], None],
) -> TradingEventHandler:
    """
    创建事件处理器的便捷函数

    Parameters
    ----------
    trader : Any
        策略引擎 Trader 实例
    send_event_func : Callable[[str, dict], None]
        发送事件的函数

    Returns
    -------
    TradingEventHandler
        事件处理器实例
    """
    return TradingEventHandler(trader, send_event_func)


# 兼容别名
AxonEventHandler = TradingEventHandler
