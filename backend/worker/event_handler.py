# -*- coding: utf-8 -*-
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
import json as _json
from datetime import datetime as _dt
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class EventBufferConfig:
    """事件缓冲配置"""
    buffer_size: int = 1000
    flush_interval: float = 1.0
    batch_size: int = 100


class EventHandler:
    """
    事件处理器

    负责处理 Worker 中的各类事件，并将事件同步到主进程。
    """

    def __init__(
        self,
        worker_id: str,
        comm_client: Any,
        config: Optional[EventBufferConfig] = None,
    ):
        self.worker_id = worker_id
        self.comm_client = comm_client
        self.config = config or EventBufferConfig()

        # 事件缓冲
        self._event_buffer: deque = deque(maxlen=self.config.buffer_size)
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

        # 统计
        self._events_received = 0
        self._events_sent = 0
        self._events_dropped = 0

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
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # 刷新剩余事件
        await self._flush_buffer()

        logger.info(f"Worker {self.worker_id} 事件处理器已停止")

    def on_order_event(self, event: Dict[str, Any]) -> None:
        """处理订单事件"""
        self._events_received += 1
        self._buffer_event({
            "type": "order",
            "data": event,
            "timestamp": datetime.now().isoformat(),
        })

    def on_fill_event(self, event: Dict[str, Any]) -> None:
        """处理成交事件"""
        self._events_received += 1
        self._buffer_event({
            "type": "fill",
            "data": event,
            "timestamp": datetime.now().isoformat(),
        })
        # 成交事件立即发送（如果有运行的事件循环）
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._flush_buffer())
        except RuntimeError:
            # 没有运行的事件循环，不立即刷新
            pass

    def on_position_event(self, event: Dict[str, Any]) -> None:
        """处理持仓事件"""
        self._events_received += 1
        self._buffer_event({
            "type": "position",
            "data": event,
            "timestamp": datetime.now().isoformat(),
        })

    def _buffer_event(self, event: Dict[str, Any]) -> None:
        """将事件添加到缓冲队列"""
        if len(self._event_buffer) >= self.config.buffer_size:
            self._events_dropped += 1
            logger.warning(f"Worker {self.worker_id} 事件缓冲区已满，丢弃事件")

        self._event_buffer.append(event)

        # 达到批量大小立即刷新（如果有运行的事件循环）
        if len(self._event_buffer) >= self.config.batch_size:
            try:
                loop = asyncio.get_running_loop()
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

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "events_received": self._events_received,
            "events_sent": self._events_sent,
            "events_dropped": self._events_dropped,
            "buffer_size": len(self._event_buffer),
        }


__all__ = [
    "EventHandler",
    "EventBufferConfig",
    "NautilusEventHandler",
    "LiveTradeRecorder",
    "create_event_handler",
]


# ============================================================================
# Nautilus 事件处理器
# ============================================================================

class NautilusEventHandler:
    """
    Nautilus 事件处理器

    订阅 Nautilus 事件并通过回调函数发送到主进程。
    """

    def __init__(
        self,
        trader: Any,
        event_callback: Callable[[str, dict], None],
    ):
        """
        初始化事件处理器

        Parameters
        ----------
        trader : Any
            Nautilus Trader 实例
        event_callback : Callable[[str, dict], None]
            事件回调函数，接收 (event_type, event_data)
        """
        self.trader = trader
        self.event_callback = event_callback
        self._subscribed = False

    def subscribe_events(self) -> None:
        """订阅 Nautilus 事件"""
        if self._subscribed:
            return
        # 获取消息总线
        msg_bus = self.trader.msg_bus
        # 订阅订单事件 (nautilus msg_bus topic: events.order.{strategy_id})
        msg_bus.subscribe(
            topic="events.order.*",
            handler=self._handle_order_event,
        )

        # 订阅成交事件 (nautilus msg_bus topic: events.fills.{instrument_id})
        msg_bus.subscribe(
            topic="events.fills.*",
            handler=self._handle_fill_event,
        )

        # 订阅持仓事件 (nautilus msg_bus topic: events.position.{strategy_id})
        msg_bus.subscribe(
            topic="events.position.*",
            handler=self._handle_position_event,
        )
        self._subscribed = True

    def unsubscribe_events(self) -> None:
        """取消订阅 Nautilus 事件"""
        if not self._subscribed:
            return
        msg_bus = self.trader.msg_bus
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


class LiveTradeRecorder:
    """
    Nautilus 事件到数据库的持久化记录器。

    在 daemon 线程中运行，订阅 nautilus_trader 的 msg_bus 事件，
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

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def subscribe(self, trader: Any) -> None:
        """订阅 msg_bus 事件（需在 node.build() 之后、node.run() 之前调用）"""
        if self._subscribed:
            return

        self._trader = trader
        msg_bus = trader.msg_bus

        # order events: events.order.{strategy_id}
        msg_bus.subscribe(topic="events.order.*", handler=self._on_order_event)
        # fill events: events.fills.{instrument_id}
        msg_bus.subscribe(topic="events.fills.*", handler=self._on_fill_event)
        # position events: events.position.{strategy_id}
        msg_bus.subscribe(topic="events.position.*", handler=self._on_position_event)

        self._subscribed = True
        logger.info(f"LiveTradeRecorder: worker_id={self.worker_id} 已订阅 msg_bus 事件")

    def unsubscribe(self) -> None:
        """取消订阅"""
        if not self._subscribed or self._trader is None:
            return

        msg_bus = self._trader.msg_bus
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
                f"LiveTradeRecorder order event error "
                f"(worker_id={self.worker_id}): {e}",
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
                f"LiveTradeRecorder fill event error "
                f"(worker_id={self.worker_id}): {e}",
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
                f"LiveTradeRecorder position event error "
                f"(worker_id={self.worker_id}): {e}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # 内部处理逻辑
    # ------------------------------------------------------------------

    def _dispatch_order_event(self, db: Any, event: Any) -> None:
        """根据事件子类型分发到对应的处理方法"""
        from nautilus_trader.core.events import (
            OrderAccepted,
            OrderCanceled,
            OrderRejected,
            OrderFilled,
        )

        # OrderFilled 同时也会出现在 order topic，优先走 fill 路径
        if isinstance(event, OrderFilled):
            self._handle_fill(db, event)
        elif isinstance(event, OrderAccepted):
            self._handle_order_accepted(db, event)
        elif isinstance(event, OrderCanceled):
            self._handle_order_canceled(db, event)
        elif isinstance(event, OrderRejected):
            self._handle_order_rejected(db, event)
        else:
            logger.debug(
                f"LiveTradeRecorder: 忽略未知订单事件类型 "
                f"{type(event).__name__} (worker_id={self.worker_id})"
            )

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
        logger.info(
            f"LiveTradeRecorder: ACCEPTED order {order_data['client_order_id']} "
            f"(worker_id={self.worker_id})"
        )

    # -- OrderCanceled ---------------------------------------------------

    def _handle_order_canceled(self, db: Any, event: Any) -> None:
        """更新订单状态为 CANCELED"""
        from . import crud

        order = crud.get_worker_order_by_id(
            db, self.worker_id, str(event.client_order_id)
        )
        if order:
            venue_oid = str(getattr(event, "venue_order_id", "")) or ""
            crud.update_worker_order_status(
                db, order.id, "CANCELED", 0.0, 0.0, 0.0, venue_oid
            )
            logger.info(
                f"LiveTradeRecorder: CANCELED order {event.client_order_id} "
                f"(worker_id={self.worker_id})"
            )
        else:
            logger.warning(
                f"LiveTradeRecorder: CANCELED order {event.client_order_id} "
                f"not found in DB (worker_id={self.worker_id})"
            )

    # -- OrderRejected ---------------------------------------------------

    def _handle_order_rejected(self, db: Any, event: Any) -> None:
        """更新订单状态为 REJECTED"""
        from . import crud

        order = crud.get_worker_order_by_id(
            db, self.worker_id, str(event.client_order_id)
        )
        if order:
            reason = str(getattr(event, "reason", ""))
            crud.update_worker_order_status(
                db, order.id, "REJECTED", 0.0, 0.0, 0.0, ""
            )
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
            "raw_data": _json.dumps({
                "strategy_id": str(getattr(event, "strategy_id", "")),
                "instrument_id": str(event.instrument_id),
                "client_order_id": str(event.client_order_id),
                "venue_order_id": str(getattr(event, "venue_order_id", "")),
                "trade_id": str(event.trade_id),
                "last_qty": str(event.last_qty),
                "last_px": str(event.last_px),
                "liquidity_side": str(getattr(event, "liquidity_side", "")),
                "ts_event": getattr(event, "ts_event", None),
            }, default=str),
        }

        crud.create_trade_if_not_exists(db, trade_data)
        logger.info(
            f"LiveTradeRecorder: FILLED trade {trade_data['trade_id']} "
            f"{trade_data['symbol']} {trade_data['side']} "
            f"qty={trade_data['quantity']} px={trade_data['price']} "
            f"(worker_id={self.worker_id})"
        )

        # --- 更新 order 状态 ---
        order = crud.get_worker_order_by_id(
            db, self.worker_id, str(event.client_order_id)
        )
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
        if hasattr(commission, "as_double"):
            return float(commission.as_double())
        if hasattr(commission, "amount"):
            return float(commission.amount)
        try:
            return float(commission)
        except (TypeError, ValueError):
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
) -> NautilusEventHandler:
    """
    创建事件处理器的便捷函数

    Parameters
    ----------
    trader : Any
        Nautilus Trader 实例
    send_event_func : Callable[[str, dict], None]
        发送事件的函数

    Returns
    -------
    NautilusEventHandler
        事件处理器实例
    """
    return NautilusEventHandler(trader, send_event_func)
