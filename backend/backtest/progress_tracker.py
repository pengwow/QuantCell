# -*- coding: utf-8 -*-
"""
回测任务进度跟踪器

提供回测任务的实时进度跟踪功能，包括：
- 创建和更新任务进度
- 查询任务进度
- 标记任务完成或失败
- 内存清理机制

使用单例模式确保全局唯一的进度管理器实例。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-14
"""

import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class BacktestStage(str, Enum):
    """回测阶段枚举"""
    DATA_PREP = "data_prep"      # 数据准备阶段
    EXECUTION = "execution"      # 执行回测阶段
    ANALYSIS = "analysis"        # 结果统计阶段
    COMPLETED = "completed"      # 已完成


class StageStatus(str, Enum):
    """阶段状态枚举"""
    PENDING = "pending"          # 等待中
    RUNNING = "running"          # 进行中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败


class DataPrepStep(str, Enum):
    """数据准备阶段子步骤"""
    CHECKING = "checking"        # 检查数据完整性
    DOWNLOADING = "downloading"  # 下载缺失数据
    LOADING = "loading"          # 加载数据


class DataPrepProgress(BaseModel):
    """数据准备阶段进度模型"""
    status: StageStatus = Field(default=StageStatus.PENDING, description="阶段状态")
    progress: float = Field(default=0.0, ge=0.0, le=100.0, description="进度百分比")
    current_step: DataPrepStep = Field(default=DataPrepStep.CHECKING, description="当前步骤")
    checked_symbols: int = Field(default=0, ge=0, description="已检查货币对数量")
    total_symbols: int = Field(default=0, ge=0, description="总货币对数量")
    downloading: Optional[Dict[str, Any]] = Field(default=None, description="下载进度信息")
    message: Optional[str] = Field(default=None, description="状态消息")

    class Config:
        use_enum_values = True


class ExecutionProgress(BaseModel):
    """执行阶段进度模型"""
    status: StageStatus = Field(default=StageStatus.PENDING, description="阶段状态")
    progress: float = Field(default=0.0, ge=0.0, le=100.0, description="进度百分比")
    current_symbol: str = Field(default="", description="当前处理的货币对")
    completed_symbols: int = Field(default=0, ge=0, description="已完成货币对数量")
    total_symbols: int = Field(default=0, ge=0, description="总货币对数量")
    message: Optional[str] = Field(default=None, description="状态消息")

    class Config:
        use_enum_values = True


class AnalysisProgress(BaseModel):
    """结果统计阶段进度模型"""
    status: StageStatus = Field(default=StageStatus.PENDING, description="阶段状态")
    progress: float = Field(default=0.0, ge=0.0, le=100.0, description="进度百分比")
    message: Optional[str] = Field(default=None, description="状态消息")

    class Config:
        use_enum_values = True


class ErrorInfo(BaseModel):
    """错误信息模型"""
    stage: str = Field(..., description="发生错误的阶段")
    message: str = Field(..., description="错误消息")


class BacktestProgress(BaseModel):
    """
    回测任务进度数据模型
    
    包含回测任务的完整进度信息，包括各阶段的详细进度。
    """
    task_id: str = Field(..., description="任务ID")
    status: StageStatus = Field(default=StageStatus.PENDING, description="任务状态")
    current_stage: BacktestStage = Field(default=BacktestStage.DATA_PREP, description="当前阶段")
    overall_progress: float = Field(default=0.0, ge=0.0, le=100.0, description="总体进度百分比")
    
    # 各阶段进度
    data_prep: DataPrepProgress = Field(default_factory=DataPrepProgress, description="数据准备阶段")
    execution: ExecutionProgress = Field(default_factory=ExecutionProgress, description="执行阶段")
    analysis: AnalysisProgress = Field(default_factory=AnalysisProgress, description="结果统计阶段")
    
    # 错误信息
    error: Optional[ErrorInfo] = Field(default=None, description="错误信息")
    
    # 时间戳
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="更新时间")

    class Config:
        use_enum_values = True


class BacktestProgressTracker:
    """
    回测任务进度跟踪器（单例模式）
    
    提供全局唯一的回测任务进度管理功能。
    
    使用示例:
        >>> tracker = BacktestProgressTracker()
        >>> tracker.create_progress("task_123")
        >>> tracker.update_progress("task_123", "data_prep", {"progress": 50})
        >>> progress = tracker.get_progress("task_123")
        >>> tracker.complete_progress("task_123")
    """
    
    # 单例实例
    _instance: Optional['BacktestProgressTracker'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'BacktestProgressTracker':
        """确保单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化进度跟踪器"""
        if self._initialized:
            return
        
        self._initialized = True
        # 存储所有任务进度的字典
        self._progresses: Dict[str, BacktestProgress] = {}
        # 线程锁，确保线程安全
        self._progress_lock = threading.Lock()
        # WebSocket 回调函数字典
        self._ws_callbacks: Dict[str, Any] = {}
        # 启动内存清理线程
        self._start_cleanup_thread()
        
        logger.info("BacktestProgressTracker 初始化完成")
    
    def _start_cleanup_thread(self):
        """启动内存清理线程，定期清理已完成的任务"""
        def cleanup_task():
            while True:
                time.sleep(300)  # 每5分钟清理一次
                try:
                    self._cleanup_completed_tasks()
                except Exception as e:
                    logger.error(f"清理任务进度时出错: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        cleanup_thread.start()
        logger.info("进度跟踪器内存清理线程已启动")
    
    def _cleanup_completed_tasks(self):
        """清理已完成或失败超过1小时的任务"""
        with self._progress_lock:
            current_time = datetime.now(timezone.utc)
            tasks_to_remove = []
            
            for task_id, progress in self._progresses.items():
                # 解析更新时间
                try:
                    updated_at = datetime.fromisoformat(progress.updated_at.replace('Z', '+00:00'))
                    time_diff = (current_time - updated_at).total_seconds()
                    
                    # 如果任务已完成/失败/停止超过1小时，标记为可删除
                    if progress.status in [StageStatus.COMPLETED, StageStatus.FAILED] and time_diff > 3600:
                        tasks_to_remove.append(task_id)
                except Exception as e:
                    logger.warning(f"解析任务 {task_id} 更新时间失败: {e}")
            
            # 删除过期任务
            for task_id in tasks_to_remove:
                del self._progresses[task_id]
                logger.info(f"已清理过期任务进度: {task_id}")
            
            if tasks_to_remove:
                logger.info(f"共清理 {len(tasks_to_remove)} 个过期任务进度")
    
    def create_progress(self, task_id: str) -> BacktestProgress:
        """
        创建新的任务进度记录
        
        Args:
            task_id: 任务唯一标识
            
        Returns:
            BacktestProgress: 创建的进度对象
        """
        with self._progress_lock:
            progress = BacktestProgress(task_id=task_id)
            self._progresses[task_id] = progress
            logger.info(f"创建任务进度记录: {task_id}")
            return progress
    
    def get_progress(self, task_id: str) -> Optional[BacktestProgress]:
        """
        获取任务进度
        
        Args:
            task_id: 任务唯一标识
            
        Returns:
            Optional[BacktestProgress]: 进度对象，如果不存在则返回 None
        """
        with self._progress_lock:
            return self._progresses.get(task_id)
    
    def update_progress(
        self,
        task_id: str,
        stage: str,
        data: Dict[str, Any]
    ) -> Optional[BacktestProgress]:
        """
        更新任务进度
        
        Args:
            task_id: 任务唯一标识
            stage: 阶段名称 (data_prep, execution, analysis)
            data: 更新的数据字典
            
        Returns:
            Optional[BacktestProgress]: 更新后的进度对象
        """
        with self._progress_lock:
            progress = self._progresses.get(task_id)
            if not progress:
                logger.warning(f"尝试更新不存在的任务进度: {task_id}")
                return None
            
            # 更新时间戳
            progress.updated_at = datetime.now(timezone.utc).isoformat()
            
            # 更新对应阶段的进度
            if stage == "data_prep":
                self._update_data_prep(progress, data)
                progress.current_stage = BacktestStage.DATA_PREP
            elif stage == "execution":
                self._update_execution(progress, data)
                progress.current_stage = BacktestStage.EXECUTION
            elif stage == "analysis":
                self._update_analysis(progress, data)
                progress.current_stage = BacktestStage.ANALYSIS
            elif stage == "overall":
                # 更新总体进度
                if "progress" in data:
                    progress.overall_progress = data["progress"]
                if "status" in data:
                    progress.status = StageStatus(data["status"])
            
            # 自动计算总体进度
            self._calculate_overall_progress(progress)
            
            logger.debug(f"更新任务 {task_id} 的 {stage} 阶段进度")
            
            # 触发 WebSocket 回调
            self._notify_ws_callbacks(task_id, progress)
            
            return progress
    
    def _update_data_prep(self, progress: BacktestProgress, data: Dict[str, Any]):
        """更新数据准备阶段进度"""
        if "status" in data:
            progress.data_prep.status = StageStatus(data["status"])
        if "progress" in data:
            progress.data_prep.progress = data["progress"]
        if "current_step" in data:
            progress.data_prep.current_step = DataPrepStep(data["current_step"])
        if "checked_symbols" in data:
            progress.data_prep.checked_symbols = data["checked_symbols"]
        if "total_symbols" in data:
            progress.data_prep.total_symbols = data["total_symbols"]
        if "downloading" in data:
            progress.data_prep.downloading = data["downloading"]
        if "message" in data:
            progress.data_prep.message = data["message"]
    
    def _update_execution(self, progress: BacktestProgress, data: Dict[str, Any]):
        """更新执行阶段进度"""
        if "status" in data:
            progress.execution.status = StageStatus(data["status"])
        if "progress" in data:
            progress.execution.progress = data["progress"]
        if "current_symbol" in data:
            progress.execution.current_symbol = data["current_symbol"]
        if "completed_symbols" in data:
            progress.execution.completed_symbols = data["completed_symbols"]
        if "total_symbols" in data:
            progress.execution.total_symbols = data["total_symbols"]
        if "message" in data:
            progress.execution.message = data["message"]
    
    def _update_analysis(self, progress: BacktestProgress, data: Dict[str, Any]):
        """更新结果统计阶段进度"""
        if "status" in data:
            progress.analysis.status = StageStatus(data["status"])
        if "progress" in data:
            progress.analysis.progress = data["progress"]
        if "message" in data:
            progress.analysis.message = data["message"]
    
    def _calculate_overall_progress(self, progress: BacktestProgress):
        """计算总体进度
        
        数据准备阶段占 30%，执行阶段占 60%，结果统计阶段占 10%
        """
        data_prep_weight = 0.3
        execution_weight = 0.6
        analysis_weight = 0.1
        
        overall = (
            progress.data_prep.progress * data_prep_weight +
            progress.execution.progress * execution_weight +
            progress.analysis.progress * analysis_weight
        )
        
        progress.overall_progress = round(overall, 2)
    
    def complete_progress(self, task_id: str) -> Optional[BacktestProgress]:
        """
        标记任务完成
        
        Args:
            task_id: 任务唯一标识
            
        Returns:
            Optional[BacktestProgress]: 更新后的进度对象
        """
        with self._progress_lock:
            progress = self._progresses.get(task_id)
            if not progress:
                return None
            
            progress.status = StageStatus.COMPLETED
            progress.current_stage = BacktestStage.COMPLETED
            progress.overall_progress = 100.0
            progress.data_prep.status = StageStatus.COMPLETED
            progress.data_prep.progress = 100.0
            progress.execution.status = StageStatus.COMPLETED
            progress.execution.progress = 100.0
            progress.analysis.status = StageStatus.COMPLETED
            progress.analysis.progress = 100.0
            progress.updated_at = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"任务完成: {task_id}")
            
            # 触发 WebSocket 回调
            self._notify_ws_callbacks(task_id, progress)
            
            return progress
    
    def fail_progress(self, task_id: str, error_message: str, stage: str = "") -> Optional[BacktestProgress]:
        """
        标记任务失败
        
        Args:
            task_id: 任务唯一标识
            error_message: 错误消息
            stage: 发生错误的阶段
            
        Returns:
            Optional[BacktestProgress]: 更新后的进度对象
        """
        with self._progress_lock:
            progress = self._progresses.get(task_id)
            if not progress:
                return None
            
            progress.status = StageStatus.FAILED
            progress.error = ErrorInfo(
                stage=stage or progress.current_stage.value,
                message=error_message
            )
            progress.updated_at = datetime.now(timezone.utc).isoformat()
            
            # 更新当前阶段状态为失败
            if progress.current_stage == BacktestStage.DATA_PREP:
                progress.data_prep.status = StageStatus.FAILED
            elif progress.current_stage == BacktestStage.EXECUTION:
                progress.execution.status = StageStatus.FAILED
            elif progress.current_stage == BacktestStage.ANALYSIS:
                progress.analysis.status = StageStatus.FAILED
            
            logger.error(f"任务失败: {task_id}, 错误: {error_message}")
            
            # 触发 WebSocket 回调
            self._notify_ws_callbacks(task_id, progress)
            
            return progress
    
    def stop_progress(self, task_id: str) -> Optional[BacktestProgress]:
        """
        标记任务已停止
        
        Args:
            task_id: 任务唯一标识
            
        Returns:
            Optional[BacktestProgress]: 更新后的进度对象
        """
        with self._progress_lock:
            progress = self._progresses.get(task_id)
            if not progress:
                return None
            
            progress.status = StageStatus.FAILED
            progress.error = ErrorInfo(
                stage=progress.current_stage.value,
                message="任务已停止"
            )
            progress.updated_at = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"任务已停止: {task_id}")
            
            # 触发 WebSocket 回调
            self._notify_ws_callbacks(task_id, progress)
            
            return progress
    
    def delete_progress(self, task_id: str) -> bool:
        """
        删除任务进度记录
        
        Args:
            task_id: 任务唯一标识
            
        Returns:
            bool: 是否删除成功
        """
        with self._progress_lock:
            if task_id in self._progresses:
                del self._progresses[task_id]
                logger.info(f"删除任务进度记录: {task_id}")
                return True
            return False
    
    def register_ws_callback(self, task_id: str, callback: Any):
        """
        注册 WebSocket 回调函数
        
        Args:
            task_id: 任务唯一标识
            callback: 回调函数
        """
        self._ws_callbacks[task_id] = callback
        logger.debug(f"注册 WebSocket 回调: {task_id}")
    
    def unregister_ws_callback(self, task_id: str):
        """
        注销 WebSocket 回调函数
        
        Args:
            task_id: 任务唯一标识
        """
        if task_id in self._ws_callbacks:
            del self._ws_callbacks[task_id]
            logger.debug(f"注销 WebSocket 回调: {task_id}")
    
    def _notify_ws_callbacks(self, task_id: str, progress: BacktestProgress):
        """通知 WebSocket 回调"""
        callback = self._ws_callbacks.get(task_id)
        if callback:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"WebSocket 回调执行失败: {e}")
    
    def get_all_progresses(self) -> Dict[str, BacktestProgress]:
        """
        获取所有任务进度
        
        Returns:
            Dict[str, BacktestProgress]: 所有任务进度的副本
        """
        with self._progress_lock:
            return dict(self._progresses)
    
    def get_active_tasks_count(self) -> int:
        """
        获取正在运行的任务数量
        
        Returns:
            int: 正在运行的任务数量
        """
        with self._progress_lock:
            return sum(
                1 for p in self._progresses.values()
                if p.status == StageStatus.RUNNING
            )


# 全局进度跟踪器实例
def get_progress_tracker() -> BacktestProgressTracker:
    """获取全局进度跟踪器实例"""
    return BacktestProgressTracker()
