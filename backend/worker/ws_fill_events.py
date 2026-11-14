"""策略成交 WebSocket 广播 helper（paper/live 成交同步链路共用）。

统一走 websocket/manager.py 的 message_queue（core/lifespan.py 的 kline 推送
同款线程安全先例）；worker/state.py 的 connection_manager 是 worker 专用通道
（前端不连），勿混用。
"""

import time
from uuid import uuid4

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


def _norm_symbol(symbol: str) -> str:
    """统一符号口径："BTC/USDT:USDT"(ccxt 永续) / "BTC-USDT" / "BTC/USDT" → "BTCUSDT"。"""
    base = str(symbol or "").split(":")[0]
    return base.replace("/", "").replace("-", "").upper()


def resolve_worker_strategy_id(worker_id: int) -> str:
    """worker_id → 已绑定策略 id，无绑定/异常回退空串（广播是旁路观测，不能抛）。"""
    try:
        # 函数内 import：worker.models 位于同包循环链内，与 live_trade_sync 等口径一致
        from worker.models import Worker

        with get_db_session() as db:
            row = (
                db.query(Worker.strategy_id)
                .filter(Worker.id == int(worker_id))
                .first()
            )
        if row and row[0] is not None:
            return str(row[0])
    except Exception as e:
        logger.warning(f"解析 worker strategy_id 失败 (worker_id={worker_id}): {e}")
    return ""


def broadcast_strategy_fill(
    *,
    worker_id: str,
    strategy_id: str,
    symbol: str,
    side: str,
    price: float,
    quantity: float,
    ts: int,
) -> None:
    """广播单笔策略成交到前端，任何失败仅 warning，绝不打断成交入账主流程。"""
    try:
        # 函数内 import：worker 泵线程进程可能未启动 WS 栈，避免模块装载期副作用
        from websocket.manager import manager

        message_queue = getattr(manager, "message_queue", None)
        if message_queue is None:
            return
        message_queue.put_nowait(
            {
                "type": "strategy.fill",
                "topic": "strategy.fill",
                "id": f"fill_{uuid4().hex[:12]}",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "worker_id": str(worker_id),
                    "strategy_id": str(strategy_id),
                    "symbol": _norm_symbol(symbol),
                    "side": str(side or "").lower(),
                    "price": float(price),
                    "quantity": float(quantity),
                    "ts": int(ts),
                },
            }
        )
    except Exception as e:
        # LoggerWrapper 不支持 exc_info，warning 自带 worker/strategy 上下文即可定位
        logger.warning(
            f"策略成交广播失败: worker_id={worker_id} strategy_id={strategy_id}: {e}"
        )
