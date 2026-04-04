# 任务管理器，用于管理下载任务和进度追踪

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import time
import asyncio
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from websocket.manager import manager
from collector.db.models import Task

class TaskStatus(str, Enum):
    """任务状态枚举
    """
    PENDING = "pending"  # 等待中
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class TaskManager:
    """任务管理器，用于管理下载任务和进度追踪
    
    实现单例模式，确保全局只有一个任务管理器实例
    同时更新内存和数据库
    """
    
    _instance = None
    
    def __new__(cls):
        """创建单例实例
        
        Returns:
            TaskManager: 任务管理器实例
        """
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
            cls._instance._tasks = {}
            cls._instance._loaded = False  # 添加加载标志
        return cls._instance
    
    def __init__(self):
        """初始化任务管理器
        """
        if not hasattr(self, '_tasks'):
            self._tasks = {}
            self._loaded = False
    
    def init(self):
        """初始化任务管理器，从数据库加载任务
        
        应用启动后调用此方法，确保数据库表已创建
        """
        if not self._loaded:
            self._load_tasks_from_db()
            self._loaded = True
    
    def _load_tasks_from_db(self):
        """从数据库加载任务数据
        
        当表不存在时，只记录警告而不抛出异常
        """
        try:
            from ..db.models import TaskBusiness

            # 从数据库获取所有任务
            tasks_from_db = TaskBusiness.get_all()
            
            # 更新内存中的任务字典
            self._tasks.update(tasks_from_db)
            
            logger.info(f"从数据库加载了 {len(tasks_from_db)} 个任务")
        except Exception as e:
            # 当表不存在时，只记录警告而不抛出异常
            logger.warning(f"从数据库加载任务失败: {e}")
            # 不抛出异常，允许应用继续运行
            logger.debug(f"加载任务失败详情: {e}")
    
    def create_task(self, task_type: str, **kwargs) -> str:
        """创建新任务
        
        Args:
            task_type: 任务类型，如"crypto_download"
            **kwargs: 任务参数
            
        Returns:
            str: 任务ID
        """
        # 生成唯一任务ID
        task_id = str(uuid.uuid4())
        
        # 创建任务信息
        task_info = {
            "task_id": task_id,
            "task_type": task_type,
            "status": TaskStatus.PENDING,
            "progress": {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "current": "",
                "percentage": 0
            },
            "params": kwargs,
            "start_time": None,
            "end_time": None,
            "error_message": None
        }
        
        # 添加到任务字典
        self._tasks[task_id] = task_info
        
        # 保存到数据库
        try:
            from ..db.models import TaskBusiness
            TaskBusiness.create(task_id, task_type, kwargs)
        except Exception as e:
            logger.error(f"保存任务到数据库失败: task_id={task_id}, error={e}")
        
        logger.info(f"创建新任务: {task_id}, 类型: {task_type}")
        
        return task_id
    
    def start_task(self, task_id: str) -> bool:
        """开始任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 成功返回True，失败返回False
        """
        if task_id not in self._tasks:
            logger.error(f"任务不存在: {task_id}")
            return False
        
        # 更新内存中的任务状态
        self._tasks[task_id]["status"] = TaskStatus.RUNNING
        self._tasks[task_id]["start_time"] = datetime.now()
        
        # 更新数据库中的任务状态
        try:
            from ..db.models import TaskBusiness
            TaskBusiness.start(task_id)
        except Exception as e:
            logger.error(f"更新数据库任务状态失败: task_id={task_id}, error={e}")
        
        logger.info(f"开始任务: {task_id}")
        return True
    
    def update_progress(self, task_id: str, current: str, completed: int, total: int, failed: int = 0, status: str = "", symbol_progress: Optional[float] = None, is_per_symbol: bool = False, interval: str = "") -> bool:
        """更新任务进度 - 只推送单个任务进度，不计算总体进度

        Args:
            task_id: 任务ID
            current: 当前正在处理的项目（货币对名称）
            completed: 已完成的项目数
            total: 总项目数
            failed: 失败的项目数，默认为0
            status: 详细的状态描述，例如"Downloaded 2025-11-01"
            symbol_progress: 该货币对的独立进度百分比（0-100）
            is_per_symbol: 是否为按货币对进度
            interval: 时间周期（如 "15m", "1h"）

        Returns:
            bool: 成功返回True，失败返回False
        """
        if task_id not in self._tasks:
            logger.error(f"任务不存在: {task_id}")
            return False

        # 计算进度百分比，确保不超过100%
        if symbol_progress is not None:
            percentage = min(100, max(0, float(symbol_progress)))
        else:
            percentage = 0.0
            if total > 0:
                percentage = min(100.0, float((completed + failed) / total * 100))

        symbol = current
        task_key = f"{interval}:{symbol}" if interval else symbol

        # 只保留单个任务的进度信息
        progress_info = {
            "symbol": symbol,
            "interval": interval,
            "task_key": task_key,
            "percentage": percentage,
            "status": status,
        }

        self._tasks[task_id]["progress"] = progress_info

        # 更新数据库中的进度信息
        try:
            from ..db.models import TaskBusiness, TaskDetailBusiness
            TaskBusiness.update_progress(task_id, current, completed, total, failed, status)
            # 更新任务明细表
            TaskDetailBusiness.upsert(
                task_id=task_id,
                symbol=symbol,
                interval=interval,
                percentage=percentage,
                completed=completed,
                total=total,
                failed=failed,
                status_text=status
            )
        except Exception as e:
            logger.error(f"更新数据库任务进度失败: task_id={task_id}, error={e}")

        # 通过WebSocket推送进度更新 - 只推送单个任务进度
        try:
            message = {
                "type": "task:progress",
                "id": f"progress_{task_id}_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "task_id": task_id,
                    "progress": progress_info  # 只包含单个任务进度
                }
            }
            
            # 使用 ZMQ 发送消息给主进程广播
            try:
                logger.info(f"[ZMQ] 开始发送任务进度消息: task_id={task_id}, type={message['type']}")
                import zmq
                
                # 创建同步 ZMQ socket 发送消息 - 使用 REQ 模式（简单请求-响应）
                context = zmq.Context()
                socket = context.socket(zmq.REQ)
                socket.setsockopt(zmq.LINGER, 0)
                socket.setsockopt(zmq.SNDTIMEO, 2000)  # 2秒发送超时
                socket.setsockopt(zmq.RCVTIMEO, 2000)  # 2秒接收超时
                
                logger.info(f"[ZMQ] 连接到 tcp://127.0.0.1:5558")
                socket.connect("tcp://127.0.0.1:5558")
                
                # 发送消息（同步）
                data = {
                    "message": message,
                    "topic": "task:progress"
                }
                logger.info(f"[ZMQ] 发送数据: {data}")
                socket.send_json(data)
                logger.info(f"[ZMQ] 数据已发送，等待确认...")
                
                # 等待响应（防止内存泄漏）
                try:
                    response = socket.recv_json()
                    logger.info(f"[ZMQ] 收到响应: {response}")
                except zmq.Again:
                    logger.warning(f"[ZMQ] 等待响应超时")
                
                socket.close()
                context.term()
                
                logger.info(f"[ZMQ] 任务进度消息发送完成: task_id={task_id}")
            except Exception as e:
                logger.warning(f"ZMQ 发送失败，尝试直接广播: {e}")
                # 回退到直接广播（仅在主进程中有效）
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(manager.broadcast(message, topic="task:progress"))
                    else:
                        loop.run_until_complete(manager.broadcast(message, topic="task:progress"))
                except Exception as e2:
                    logger.error(f"直接广播也失败: {e2}")
        except Exception as e:
            logger.error(f"WebSocket推送失败: {e}", exc_info=True)
        
        logger.debug(f"更新任务进度: {task_id}, 当前: {current}, 进度: {percentage}%, 状态: {status}")
        return True
    
    def complete_task(self, task_id: str) -> bool:
        """完成任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 成功返回True，失败返回False
        """
        if task_id not in self._tasks:
            logger.error(f"任务不存在: {task_id}")
            return False

        # 更新内存中的任务状态
        self._tasks[task_id]["status"] = TaskStatus.COMPLETED
        self._tasks[task_id]["end_time"] = datetime.now()

        # 计算总体统计信息
        total_completed = 0
        total_failed = 0
        total_tasks = 0

        # 将所有子任务进度更新为100%
        try:
            if "symbols_progress" in self._tasks[task_id]:
                for task_key, progress_info in self._tasks[task_id]["symbols_progress"].items():
                    # 更新内存中的进度
                    self._tasks[task_id]["symbols_progress"][task_key]["percentage"] = 100.0
                    self._tasks[task_id]["symbols_progress"][task_key]["status"] = "completed"

                    # 累加统计信息
                    total_completed += progress_info.get("completed", 0)
                    total_failed += progress_info.get("failed", 0)
                    total_tasks += progress_info.get("total", 0)

                    # 更新数据库中的进度
                    from ..db.models import TaskDetailBusiness
                    TaskDetailBusiness.upsert(
                        task_id=task_id,
                        symbol=progress_info["symbol"],
                        interval=progress_info["interval"],
                        percentage=100.0,
                        completed=progress_info.get("total", 0),
                        total=progress_info.get("total", 0),
                        failed=progress_info.get("failed", 0),
                        status_text="completed"
                    )

                    # 推送每个子任务的完成进度
                    progress_info = {
                        "symbol": progress_info["symbol"],
                        "interval": progress_info["interval"],
                        "task_key": task_key,
                        "percentage": 100.0,
                        "status": "completed",
                    }
                    message = {
                        "type": "task:progress",
                        "id": f"progress_{task_id}_{int(time.time() * 1000)}",
                        "timestamp": int(time.time() * 1000),
                        "data": {
                            "task_id": task_id,
                            "progress": progress_info
                        }
                    }
                    try:
                        import zmq
                        context = zmq.Context()
                        socket = context.socket(zmq.REQ)
                        socket.setsockopt(zmq.LINGER, 0)
                        socket.setsockopt(zmq.SNDTIMEO, 2000)
                        socket.setsockopt(zmq.RCVTIMEO, 2000)
                        socket.connect("tcp://127.0.0.1:5558")
                        socket.send_json({"message": message, "topic": "task:progress"})
                        try:
                            socket.recv_json()
                        except zmq.Again:
                            pass
                        socket.close()
                        context.term()
                    except Exception as e:
                        logger.warning(f"推送子任务完成进度失败: {e}")

                logger.info(f"已将所有子任务进度更新为100%: task_id={task_id}, 子任务数={len(self._tasks[task_id]['symbols_progress'])}")

                # 更新总体进度统计
                if "progress" not in self._tasks[task_id]:
                    self._tasks[task_id]["progress"] = {}
                self._tasks[task_id]["progress"]["completed"] = total_completed
                self._tasks[task_id]["progress"]["failed"] = total_failed
                self._tasks[task_id]["progress"]["total"] = total_tasks

        except Exception as e:
            logger.error(f"更新子任务进度失败: task_id={task_id}, error={e}")

        # 更新数据库中的任务状态
        try:
            from ..db.models import TaskBusiness
            TaskBusiness.complete(task_id)
        except Exception as e:
            logger.error(f"更新数据库任务状态失败: task_id={task_id}, error={e}")
        
        # 通过WebSocket推送状态更新
        try:
            
            # 推送状态更新
            message = {
                "type": "task:status",
                "id": f"status_{task_id}_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "task_id": task_id,
                    "status": TaskStatus.COMPLETED,
                    "end_time": self._tasks[task_id]["end_time"]
                }
            }
            
            # 在任何线程中执行异步操作
            try:
                # 尝试获取当前事件循环
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在运行的事件循环中执行
                    loop.create_task(manager.queue_message(message, topic="task:status"))
                else:
                    # 事件循环存在但未运行，运行直到完成
                    loop.run_until_complete(manager.queue_message(message, topic="task:status"))
            except RuntimeError:
                # 没有当前事件循环，使用run_coroutine_threadsafe
                # 创建新的事件循环并运行
                asyncio.run(manager.queue_message(message, topic="task:status"))
        except Exception as e:
            logger.debug(f"WebSocket推送失败: {e}")
        
        logger.info(f"任务完成: {task_id}")
        return True
    
    def fail_task(self, task_id: str, error_message: str) -> bool:
        """标记任务失败
        
        Args:
            task_id: 任务ID
            error_message: 错误信息
            
        Returns:
            bool: 成功返回True，失败返回False
        """
        if task_id not in self._tasks:
            logger.error(f"任务不存在: {task_id}")
            return False
        
        # 更新内存中的任务状态
        self._tasks[task_id]["status"] = TaskStatus.FAILED
        self._tasks[task_id]["end_time"] = datetime.now()
        self._tasks[task_id]["error_message"] = error_message
        
        # 更新数据库中的任务状态
        try:
            from ..db.models import TaskBusiness
            TaskBusiness.fail(task_id, error_message)
        except Exception as e:
            logger.error(f"更新数据库任务状态失败: task_id={task_id}, error={e}")
        
        # 通过WebSocket推送状态更新
        try:
            
            # 推送状态更新
            message = {
                "type": "task:status",
                "id": f"status_{task_id}_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "task_id": task_id,
                    "status": TaskStatus.FAILED,
                    "end_time": self._tasks[task_id]["end_time"],
                    "error_message": error_message
                }
            }
            
            # 在任何线程中执行异步操作
            try:
                # 尝试获取当前事件循环
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在运行的事件循环中执行
                    loop.create_task(manager.queue_message(message, topic="task:status"))
                else:
                    # 事件循环存在但未运行，运行直到完成
                    loop.run_until_complete(manager.queue_message(message, topic="task:status"))
            except RuntimeError:
                # 没有当前事件循环，使用run_coroutine_threadsafe
                # 创建新的事件循环并运行
                asyncio.run(manager.queue_message(message, topic="task:status"))
        except Exception as e:
            logger.debug(f"WebSocket推送失败: {e}")
        
        logger.error(f"任务失败: {task_id}, 错误信息: {error_message}")
        return True
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Dict[str, Any]]: 任务信息，如果任务不存在则返回None
        """
        # 先从内存获取
        task = self._tasks.get(task_id)
        
        if not task:
            # 内存中没有，从数据库获取
            try:
                from ..db.models import TaskBusiness
                task = TaskBusiness.get(task_id)
                if task:
                    # 更新内存
                    self._tasks[task_id] = task
            except Exception as e:
                logger.error(f"从数据库获取任务失败: task_id={task_id}, error={e}")
        
        # 确保进度信息中包含status字段
        if task and "progress" in task and "status" not in task["progress"]:
            # 如果progress字典中没有status字段，添加它
            task["progress"]["status"] = task["progress"].get("current", "")
        
        return task
    
    def get_all_tasks(self) -> Dict[str, Any]:
        """获取所有任务信息
        
        Returns:
            Dict[str, Any]: 所有任务信息
        """
        # 确保任务已加载
        if not self._loaded:
            self._load_tasks_from_db()
            self._loaded = True
        # 先从数据库更新最新任务
        try:
            self._load_tasks_from_db()
        except Exception as e:
            logger.warning(f"更新任务列表失败: {e}")
            # 继续返回内存中的任务列表，不影响应用运行
        
        # 确保所有任务的进度信息中包含status字段
        for task_id, task in self._tasks.items():
            if "progress" in task and "status" not in task["progress"]:
                # 如果progress字典中没有status字段，添加它
                task["progress"]["status"] = task["progress"].get("current", "")
        
        return self._tasks
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 成功返回True，失败返回False
        """
        if task_id not in self._tasks:
            logger.error(f"任务不存在: {task_id}")
            return False
        
        # 从内存中删除
        del self._tasks[task_id]
        
        # 从数据库中删除
        try:
            
            Task.delete(task_id)
        except Exception as e:
            logger.error(f"从数据库删除任务失败: task_id={task_id}, error={e}")
        
        logger.info(f"删除任务: {task_id}")
        return True


# 创建全局任务管理器实例
task_manager = TaskManager()
