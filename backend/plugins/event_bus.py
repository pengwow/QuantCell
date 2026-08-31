import asyncio
import threading
from typing import TYPE_CHECKING, Any

from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__, LogType.APPLICATION)


def _callback_name(callback: Callable) -> str:
    """回调展示名。订阅方承诺的是 Callable，不一定是带 __name__ 的函数
    （functools.partial、可调用对象、测试 Mock 都没有 __name__）。"""
    return getattr(callback, "__name__", None) or type(callback).__name__


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_name: str, callback: Callable) -> None:
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)
                logger.info(f"订阅事件: {event_name} -> {_callback_name(callback)}")

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        with self._lock:
            if event_name in self._subscribers:
                try:
                    self._subscribers[event_name].remove(callback)
                    logger.info(f"取消订阅事件: {event_name} -> {_callback_name(callback)}")
                except ValueError:
                    logger.warning(f"订阅者不存在: {event_name} -> {_callback_name(callback)}")

    def publish(self, event_name: str, data: Any = None) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(event_name, []))

        for callback in subscribers:
            try:
                callback(data)
            except Exception as e:
                logger.error(
                    f"事件 {event_name} 的订阅者 {_callback_name(callback)} 执行异常",
                    exception=e,
                )

    def publish_async(self, event_name: str, data: Any = None) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(event_name, []))

        loop = asyncio.get_event_loop()

        for callback in subscribers:
            try:
                loop.run_in_executor(None, callback, data)
            except Exception as e:
                logger.error(
                    f"异步事件 {event_name} 的订阅者 {_callback_name(callback)} 启动异常",
                    exception=e,
                )

    def get_subscribers(self, event_name: str) -> list[str]:
        with self._lock:
            subscribers = list(self._subscribers.get(event_name, []))

        return [_callback_name(cb) for cb in subscribers]

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()
            logger.info("已清除所有事件订阅")


event_bus = EventBus()
