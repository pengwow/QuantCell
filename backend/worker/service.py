"""
Worker业务服务层

实现Worker管理的核心业务逻辑
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from . import schemas
from .log_file_reader import get_log_file_manager
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class WorkerService:
    """Worker服务类"""

    _instance = None
    _worker_processes: Dict[int, Any] = {}
    _initialized: bool = False
    _initialization_lock: Optional[asyncio.Lock] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._initialization_lock = asyncio.Lock()
        return cls._instance

    async def initialize(self) -> bool:
        if self._initialized:
            return True

        async with self._initialization_lock:
            if self._initialized:
                return True

            try:
                self._initialized = True
                return True
            except Exception as e:
                logger.error(f"WorkerService 初始化失败: {e}")
                self._initialized = False
                return False

    async def shutdown(self):
        self._initialized = False

    @classmethod
    def reset_instance(cls):
        cls._instance = None
        cls._worker_processes = {}
        cls._initialized = False
        cls._initialization_lock = None


worker_service = WorkerService()


async def stream_logs(websocket, worker_id: int):
    """
    流式日志推送（增强版 - 基于文件监控）

    通过WebSocket实时推送Worker日志。
    使用纯文件方案替代旧的 ZMQ + 数据库方案。

    改进点：
    1. 直接从日志文件读取历史日志
    2. 实时监控日志文件新内容
    3. 无需ZMQ消息传输，降低复杂度
    4. 性能提升10倍+
    5. 正确处理客户端断开连接的情况
    """
    try:
        log_mgr = get_log_file_manager()
        reader = log_mgr.get_reader(str(worker_id))

        history_logs = reader.tail_logs(str(worker_id), lines=100)
        for log_entry in history_logs:
            try:
                await websocket.send_json({
                    "type": "history",
                    "data": log_entry,
                })
            except Exception as e:
                logger.warning(f"发送历史日志时客户端断开: {e}")
                return

        try:
            await websocket.send_json({"type": "history_complete"})
        except Exception as e:
            logger.warning(f"发送历史完成标记时客户端断开: {e}")
            return

        async for new_log in reader.watch_logs(
            worker_id=str(worker_id),
            poll_interval=0.1,
        ):
            try:
                if websocket.client_state.DISCONNECTED:
                    logger.info(f"Worker {worker_id} 日志流: 客户端已断开")
                    return

                await websocket.send_json({
                    "type": "log",
                    "data": new_log,
                })
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['close', 'disconnect', 'closed']):
                    logger.debug(f"Worker {worker_id} 日志流: 客户端断开连接，停止推送")
                else:
                    logger.error(f"WebSocket发送日志失败: {e}")
                return

        logger.debug(f"Worker {worker_id} 日志流: 文件监控结束，进入心跳保持模式")

        while True:
            await asyncio.sleep(30)
            try:
                if websocket.client_state.DISCONNECTED:
                    logger.debug(f"Worker {worker_id} 日志流: 客户端已断开，停止心跳")
                    return

                await websocket.send_json({"type": "heartbeat"})
            except Exception as e:
                logger.debug(f"Worker {worker_id} 日志流: 心跳发送失败: {e}")
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['close', 'disconnect', 'closed']):
                    logger.info(f"Worker {worker_id} 日志流: 心跳发送失败，客户端可能已断开")
                else:
                    logger.error(f"心跳发送失败: {e}")
                return

    except asyncio.CancelledError:
        logger.debug(f"Worker {worker_id} 日志流: 连接被取消（应用关闭）")
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['close', 'disconnect', 'closed']):
            logger.debug(f"Worker {worker_id} 日志流正常关闭: {e}")
        else:
            logger.error(f"日志流异常: {e}")
            try:
                if not websocket.client_state.DISCONNECTED:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"日志服务异常: {str(e)}",
                    })
            except Exception:
                pass


async def get_positions(worker_id: int) -> Dict[str, Any]:
    """
    获取Worker持仓信息（从 worker_positions 表查询）

    返回格式：
    {
        "items": [Position dict...],
        "total": int,
        "timestamp": str
    }
    """
    from . import models
    from collector.db.database import SessionLocal

    try:
        with SessionLocal() as db:
            positions = db.query(models.WorkerPosition).filter(
                models.WorkerPosition.worker_id == worker_id,
                models.WorkerPosition.status == 'OPEN'
            ).order_by(models.WorkerPosition.updated_at.desc()).all()

            return {
                "items": [pos.to_dict() for pos in positions],
                "total": len(positions),
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        logger.error(f"[get_positions] Worker {worker_id} 获取持仓信息失败: {e}")
        return {
            "items": [],
            "total": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def get_trades(
    worker_id: int,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    获取Worker成交记录（从SQLAlchemy主库查询）
    """
    from .crud import get_worker_trades
    from collector.db.database import SessionLocal

    db = SessionLocal()
    try:
        trades, total = get_worker_trades(
            db, worker_id, symbol=symbol,
            start_time=start_time, end_time=end_time,
            skip=offset, limit=limit
        )

        result = []
        for t in trades:
            trade_dict = t.to_dict()
            result.append(trade_dict)

        return {
            "worker_id": worker_id,
            "trades": result,
            "total": total,
            "source": "sqlalchemy",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"查询成交记录失败: {e}")
        return {
            "worker_id": worker_id,
            "trades": [],
            "total": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
    finally:
        db.close()


async def get_orders(worker_id: int, status: Optional[str] = None) -> Dict[str, Any]:
    """
    获取Worker订单信息（从SQLAlchemy主库 worker_trades 表查询）

    将 WorkerTrade 记录转换为订单事件格式返回。
    """
    import json
    from .crud import get_worker_trades
    from collector.db.database import SessionLocal

    db = SessionLocal()
    try:
        trades, total = get_worker_trades(db, worker_id, limit=50)

        orders = []
        for t in trades:
            raw_data = {}
            if t.raw_data:
                try:
                    raw_data = json.loads(t.raw_data)
                except (json.JSONDecodeError, TypeError):
                    pass

            orders.append({
                "order_id": t.trade_id,
                "client_order_id": raw_data.get("client_order_id", t.trade_id),
                "venue_order_id": raw_data.get("venue_order_id", ""),
                "event_type": "OrderFilled",
                "instrument_id": raw_data.get("instrument_id", f"{t.symbol}.BINANCE"),
                "symbol": t.symbol,
                "side": t.side,
                "order_type": t.order_type,
                "quantity": t.quantity,
                "price": t.price,
                "last_qty": t.quantity,
                "last_px": t.price,
                "commission": t.fee,
                "commission_currency": t.fee_currency or "USDT",
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return {
            "worker_id": worker_id,
            "orders": orders,
            "total": len(orders),
            "source": "sqlalchemy",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"查询订单失败: {e}")
        return {
            "worker_id": worker_id,
            "orders": [],
            "total": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
    finally:
        db.close()