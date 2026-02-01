# 事件引擎
# 用于实盘模式的事件驱动架构

from queue import Queue, Empty
from threading import Thread
from typing import Callable, Dict, Any, List
import time
from loguru import logger


class EventEngine:
    """
    事件引擎
    用于实盘模式的事件驱动架构
    """
    
    def __init__(self):
        """
        初始化事件引擎
        """
        self.event_queue = Queue()
        self.handlers = {}
        self.running = False
        self.thread = None
    
    def register(self, event_type: str, handler: Callable):
        """
        注册事件处理器
        
        参数：
        - event_type: 事件类型
        - handler: 处理函数
        """
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        logger.info(f"事件处理器已注册: {event_type}")
    
    def unregister(self, event_type: str, handler: Callable):
        """
        注销事件处理器
        
        参数：
        - event_type: 事件类型
        - handler: 处理函数
        """
        if event_type in self.handlers:
            if handler in self.handlers[event_type]:
                self.handlers[event_type].remove(handler)
                logger.info(f"事件处理器已注销: {event_type}")
    
    def put(self, event_type: str, data: Any = None):
        """
        推送事件
        
        参数：
        - event_type: 事件类型
        - data: 事件数据
        """
        self.event_queue.put((event_type, data))
    
    def start(self):
        """
        启动事件引擎
        """
        self.running = True
        self.thread = Thread(target=self._process_events, daemon=True)
        self.thread.start()
        logger.info("事件引擎已启动")
    
    def stop(self):
        """
        停止事件引擎
        """
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            logger.info("事件引擎已停止")
    
    def _process_events(self):
        """
        处理事件（后台线程）
        """
        while self.running:
            try:
                event_type, data = self.event_queue.get(timeout=1)
                
                # 调用所有注册的处理器
                if event_type in self.handlers:
                    for handler in self.handlers[event_type]:
                        try:
                            handler(data)
                        except Exception as e:
                            logger.error(f"事件处理错误: {event_type}, 错误: {e}")
            except Empty:
                continue
            except Exception as e:
                logger.error(f"事件引擎错误: {e}")
                break
        logger.info("事件处理线程已退出")


class EventType:
    """
    事件类型常量
    """
    TICK = "tick"
    BAR = "bar"
    ORDER = "order"
    TRADE = "trade"
    POSITION = "position"
    ACCOUNT = "account"
    FUNDING_RATE = "funding_rate"
    ERROR = "error"
