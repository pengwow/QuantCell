# 实时引擎产出的 depth / aggTrade 数据 → WebSocket 广播信封
import time
from collections import deque
from collections.abc import Callable

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


def make_depth_push_consumer(mgr, throttle: float = 0.5, clock: Callable[[], float] = time.monotonic):
    """depth 快照广播消费者：同品种 throttle 秒内只推一次（leading-edge 节流）。

    binance depth20 本身 1s 推一条快照，throttle 仅防御订阅风暴；不做 trailing
    补发——降级窗口最多 1s，肉眼不可感知。

    Args:
        mgr: websocket manager 单例（只消费其 message_queue 属性，put_nowait 广播）
        throttle: 同品种两次推送的最小间隔（秒）
        clock: 单调时钟注入，默认 time.monotonic（测试可注入假时钟）

    Returns:
        同步消费者函数，签名与 DataDistributor 的 consumer(data) 契约一致
    """
    last_sent: dict[str, float] = {}
    seq = 0

    def push(data: dict) -> None:
        nonlocal seq
        try:
            symbol = str(data.get("symbol") or "").upper()
            if not symbol:
                return
            now = clock()
            last = last_sent.get(symbol)
            # 首条必发（未记录过上条时间时不节流），否则订阅后第一条快照会被吞掉
            if last is not None and now - last < throttle:
                return
            last_sent[symbol] = now
            queue = getattr(mgr, "message_queue", None)
            if queue is None:
                return
            seq += 1
            now_ms = int(time.time() * 1000)
            queue.put_nowait(
                {
                    "type": "depth",
                    "topic": "depth",
                    "id": f"depth_{now_ms}_{seq}",
                    "timestamp": now_ms,
                    "data": {
                        "symbol": symbol,
                        "bids": data.get("bids") or [],
                        "asks": data.get("asks") or [],
                    },
                }
            )
        except Exception as e:  # 广播失败（含队列满）不允许打断数据泵线程
            logger.warning(f"depth 广播失败，丢弃本次消息: {e}")

    return push


def make_aggtrade_push_consumer(mgr, flush_interval: float = 0.2, clock: Callable[[], float] = time.monotonic):
    """aggTrade 攒批广播消费者：flush_interval 窗口内的成交合并为一条 trades 信封。

    ponytail: 无独立定时节拍器——末批成交最迟等下一条成交触发 flush，
    低频品种 tape 延迟≈成交间隔；若不可接受，升级路径是引擎 loop 里
    挂一个每 flush_interval 扫尾的协程。

    Args:
        mgr: websocket manager 单例（只消费其 message_queue 属性，put_nowait 广播）
        flush_interval: 攒批窗口时长（秒），窗口内首笔到达开始计时
        clock: 单调时钟注入，默认 time.monotonic（测试可注入假时钟）

    Returns:
        同步消费者函数，签名与 DataDistributor 的 consumer(data) 契约一致
    """
    buffer: deque = deque(maxlen=500)  # 防御订阅风暴下窗口内无限堆积
    window_start: float | None = None
    seq = 0

    def _flush() -> None:
        nonlocal seq, window_start
        queue = getattr(mgr, "message_queue", None)
        if queue is not None and buffer:
            seq += 1
            now_ms = int(time.time() * 1000)
            queue.put_nowait(
                {
                    "type": "trades",
                    "topic": "trades",
                    "id": f"trades_{now_ms}_{seq}",
                    "timestamp": now_ms,
                    "data": list(buffer),
                }
            )
        buffer.clear()
        window_start = None

    def push(data: dict) -> None:
        nonlocal window_start
        try:
            symbol = str(data.get("symbol") or "").upper()
            price = data.get("price")
            if not symbol or price is None:
                return
            # data_processor 输出的成交时间是 timestamp（毫秒），信封内统一叫 time
            trade = {
                "symbol": symbol,
                "price": price,
                "quantity": data.get("quantity"),
                "time": data.get("timestamp"),
                "is_buyer_maker": bool(data.get("is_buyer_maker", False)),
            }
            now = clock()
            if window_start is None:
                window_start = now
            buffer.append(trade)
            if now - window_start >= flush_interval:
                _flush()
        except Exception as e:  # 广播失败（含队列满）不允许打断数据泵线程
            logger.warning(f"trades 广播失败，丢弃本次消息: {e}")

    return push
