# 任务管理器，用于管理下载任务和进度追踪

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from loguru import logger


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
    
    def update_progress(self, task_id: str, current: str, completed: int, total: int, failed: int = 0, status: str = None) -> bool:
        """更新任务进度
        
        Args:
            task_id: 任务ID
            current: 当前正在处理的项目
            completed: 已完成的项目数
            total: 总项目数
            failed: 失败的项目数，默认为0
            status: 详细的状态描述，例如"Downloaded 2025-11-01"
            
        Returns:
            bool: 成功返回True，失败返回False
        """
        if task_id not in self._tasks:
            logger.error(f"任务不存在: {task_id}")
            return False
        
        # 计算进度百分比
        percentage = 0
        if total > 0:
            percentage = int((completed + failed) / total * 100)
        
        # 更新内存中的进度信息
        self._tasks[task_id]["progress"] = {
            "total": total,
            "completed": completed,
            "failed": failed,
            "current": current,
            "percentage": percentage,
            "status": status  # 添加详细的状态描述
        }
        
        # 更新数据库中的进度信息
        try:
            from ..db.models import TaskBusiness
            TaskBusiness.update_progress(task_id, current, completed, total, failed, status)
        except Exception as e:
            logger.error(f"更新数据库任务进度失败: task_id={task_id}, error={e}")
        
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
        
        # 更新数据库中的任务状态
        try:
            from ..db.models import TaskBusiness
            TaskBusiness.complete(task_id)
        except Exception as e:
            logger.error(f"更新数据库任务状态失败: task_id={task_id}, error={e}")
        
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
            from ..db.models import Task
            Task.delete(task_id)
        except Exception as e:
            logger.error(f"从数据库删除任务失败: task_id={task_id}, error={e}")
        
        logger.info(f"删除任务: {task_id}")
        return True


# 创建全局任务管理器实例
task_manager = TaskManager()
