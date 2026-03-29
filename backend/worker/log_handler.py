"""
Worker 日志处理器

将 Worker 进程的日志发送到主进程，并写入数据库
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from queue import Queue, Empty
import threading
import time
import sys
import zmq

from .ipc.protocol import Message, MessageType, serialize_message

# 尝试导入 loguru
from loguru import logger as loguru_logger


class WorkerLogHandler(logging.Handler):
    """
    Worker 日志处理器

    捕获 Worker 进程的日志，发送到主进程
    支持标准 logging 和 loguru
    """

    def __init__(self, worker_id: str, comm_client=None, level=logging.NOTSET):
        super().__init__(level)
        self.worker_id = worker_id
        self.comm_client = comm_client
        self._queue = Queue()
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None
        # 直接使用 ZMQ 发送，不依赖 comm_client 的事件循环
        self._zmq_context: Optional[zmq.Context] = None
        self._zmq_socket: Optional[zmq.Socket] = None
        
        # 如果 comm_client 不为空，立即启动发送线程
        if comm_client:
            self._start_flush_thread()

    def set_comm_client(self, comm_client):
        """设置通信客户端"""
        self.comm_client = comm_client
        if comm_client and not self._running:
            self._start_flush_thread()

    def _init_zmq_socket(self):
        """初始化 ZMQ 套接字"""
        try:
            if self._zmq_socket:
                return True
            
            # 创建 ZMQ 上下文和 PUSH 套接字
            self._zmq_context = zmq.Context()
            self._zmq_socket = self._zmq_context.socket(zmq.PUSH)
            self._zmq_socket.setsockopt(zmq.SNDTIMEO, 1000)  # 发送超时 1 秒
            self._zmq_socket.setsockopt(zmq.LINGER, 0)  # 关闭时不等待
            
            # 连接到状态端口
            status_port = 5557  # 默认状态端口
            self._zmq_socket.connect(f"tcp://127.0.0.1:{status_port}")
            print(f"[WorkerLogHandler] ZMQ 套接字已连接到端口 {status_port}", flush=True)
            return True
        except Exception as e:
            print(f"[WorkerLogHandler] 初始化 ZMQ 套接字失败: {e}", flush=True)
            return False

    def emit(self, record: logging.LogRecord):
        """处理标准 logging 日志记录"""
        try:
            log_entry = {
                "timestamp": record.created,
                "level": record.levelname,
                "message": self.format(record),
                "source": record.name,
            }
            self._queue.put(log_entry)
        except Exception:
            self.handleError(record)

    def emit_loguru(self, message):
        """处理 loguru 日志记录"""
        try:
            record = message.record
            log_entry = {
                "timestamp": record["time"].timestamp(),
                "level": record["level"].name,
                "message": record["message"],
                "source": record["name"],
            }
            self._queue.put(log_entry)
        except Exception as e:
            print(f"[WorkerLogHandler] loguru emit error: {e}", flush=True)

    def _start_flush_thread(self):
        """启动后台发送线程"""
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
        print(f"[WorkerLogHandler] 日志发送线程已启动 for {self.worker_id}", flush=True)

    def _flush_loop(self):
        """后台发送循环"""
        print(f"[WorkerLogHandler] 发送循环开始 for {self.worker_id}", flush=True)
        
        # 初始化 ZMQ 套接字
        if not self._init_zmq_socket():
            print(f"[WorkerLogHandler] ZMQ 初始化失败，无法发送日志", flush=True)
            return
        
        while self._running:
            try:
                # 批量获取日志
                logs = []
                try:
                    # 等待至少一条日志，最多等待1秒
                    log = self._queue.get(timeout=1.0)
                    # 检查是否是停止信号
                    if log is None:
                        print(f"[WorkerLogHandler] 收到停止信号 for {self.worker_id}", flush=True)
                        break
                    logs.append(log)
                    # 批量获取更多日志
                    while len(logs) < 10:
                        try:
                            log = self._queue.get_nowait()
                            if log is None:
                                break
                            logs.append(log)
                        except Empty:
                            break
                except Empty:
                    continue

                # 发送日志
                if logs and self._zmq_socket:
                    print(f"[WorkerLogHandler] 准备发送 {len(logs)} 条日志", flush=True)
                    for log in logs:
                        try:
                            print(f"[WorkerLogHandler] 创建日志消息: {log['message'][:50]}...", flush=True)
                            message = Message.create_log(
                                worker_id=self.worker_id,
                                level=log["level"],
                                message=log["message"],
                                source=log["source"],
                            )
                            # 使用 ZMQ 直接发送
                            data = serialize_message(message)
                            self._zmq_socket.send(data, flags=zmq.NOBLOCK)
                            print(f"[WorkerLogHandler] 日志发送成功: {log['message'][:50]}...", flush=True)
                        except zmq.Again:
                            print(f"[WorkerLogHandler] 发送日志失败: ZMQ 发送缓冲区满", flush=True)
                        except Exception as e:
                            import traceback
                            print(f"[WorkerLogHandler] 发送日志失败: {e}", flush=True)
                            print(f"[WorkerLogHandler] 错误详情: {traceback.format_exc()}", flush=True)
                else:
                    print(f"[WorkerLogHandler] 无法发送日志: logs={len(logs)}, socket={self._zmq_socket is not None}", flush=True)

            except Exception as e:
                print(f"[WorkerLogHandler] 发送循环错误: {e}", flush=True)
                time.sleep(0.1)
        
        # 关闭 ZMQ 套接字
        if self._zmq_socket:
            try:
                self._zmq_socket.close()
            except:
                pass
        if self._zmq_context:
            try:
                self._zmq_context.term()
            except:
                pass
        
        print(f"[WorkerLogHandler] 发送循环结束 for {self.worker_id}", flush=True)

    def stop(self):
        """停止日志处理器"""
        print(f"[WorkerLogHandler] 停止日志处理器 for {self.worker_id}", flush=True)
        self._running = False
        
        # 向队列发送一个空消息，唤醒等待的线程
        self._queue.put(None)
        
        if self._flush_thread:
            self._flush_thread.join(timeout=3)
        
        # 关闭 ZMQ 套接字
        if self._zmq_socket:
            try:
                self._zmq_socket.close()
                self._zmq_socket = None
            except:
                pass
        if self._zmq_context:
            try:
                self._zmq_context.term()
                self._zmq_context = None
            except:
                pass
        
        print(f"[WorkerLogHandler] 日志处理器已停止 for {self.worker_id}", flush=True)

    def flush(self):
        """刷新日志队列"""
        logs = []
        try:
            while True:
                log = self._queue.get_nowait()
                logs.append(log)
        except Empty:
            pass

        if logs and self._zmq_socket:
            print(f"[WorkerLogHandler] 刷新 {len(logs)} 条日志", flush=True)
            for log in logs:
                try:
                    message = Message.create_log(
                        worker_id=self.worker_id,
                        level=log["level"],
                        message=log["message"],
                        source=log["source"],
                    )
                    data = serialize_message(message)
                    self._zmq_socket.send(data, flags=zmq.NOBLOCK)
                except Exception as e:
                    print(f"[WorkerLogHandler] 刷新日志失败: {e}", flush=True)
        else:
            print(f"[WorkerLogHandler] 刷新失败: logs={len(logs)}, socket={self._zmq_socket is not None}", flush=True)


class WorkerLoguruInterceptor:
    """
    Loguru 日志拦截器

    用于拦截 loguru 的日志并发送到 WorkerLogHandler
    """

    def __init__(self, handler: WorkerLogHandler):
        self.handler = handler

    def __call__(self, message):
        """处理 loguru 日志消息"""
        self.handler.emit_loguru(message)
