import asyncio
import threading
from typing import Any, Callable, Dict, List

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class EventBus:

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_name: str, callback: Callable) -> None:
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)
                logger.info(f"订阅事件: {event_name} -> {callback.__name__}")

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        with self._lock:
            if event_name in self._subscribers:
                try:
                    self._subscribers[event_name].remove(callback)
                    logger.info(f"取消订阅事件: {event_name} -> {callback.__name__}")
                except ValueError:
                    logger.warning(f"订阅者不存在: {event_name} -> {callback.__name__}")

    def publish(self, event_name: str, data: Any = None) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(event_name, []))

        for callback in subscribers:
            try:
                callback(data)
            except Exception as e:
                logger.error(
                    f"事件 {event_name} 的订阅者 {callback.__name__} 执行异常",
                    exception=e
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
                    f"异步事件 {event_name} 的订阅者 {callback.__name__} 启动异常",
                    exception=e
                )

    def get_subscribers(self, event_name: str) -> List[str]:
        with self._lock:
            subscribers = list(self._subscribers.get(event_name, []))

        return [getattr(cb, '__name__', type(cb).__name__) for cb in subscribers]

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()
            logger.info("已清除所有事件订阅")


event_bus = EventBus()
