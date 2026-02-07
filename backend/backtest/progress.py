# -*- coding: utf-8 -*-
"""
进度显示模块

提供回测过程中的进度显示功能，包括：
- 控制台进度条
- 进度追踪器
- 多任务进度管理
"""

import sys
import time
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProgressInfo:
    """进度信息数据类"""
    current: int = 0
    total: int = 0
    message: str = ""
    status: str = "pending"  # pending, running, completed, failed
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    
    @property
    def percentage(self) -> float:
        """获取进度百分比"""
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100
    
    @property
    def elapsed_time(self) -> float:
        """获取已用时间（秒）"""
        if self.start_time is None:
            return 0.0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    @property
    def estimated_time(self) -> float:
        """获取预估剩余时间（秒）"""
        if self.current == 0 or self.total == 0:
            return 0.0
        elapsed = self.elapsed_time
        rate = self.current / elapsed if elapsed > 0 else 0
        remaining = self.total - self.current
        return remaining / rate if rate > 0 else 0


class ConsoleProgressBar:
    """控制台进度条"""
    
    def __init__(self, total: int, desc: str = "进度", bar_length: int = 40):
        """
        初始化进度条
        
        参数：
            total: 总任务数
            desc: 进度条描述
            bar_length: 进度条长度
        """
        self.total = total
        self.desc = desc
        self.bar_length = bar_length
        self.current = 0
        self.start_time = time.time()
        
    def update(self, n: int = 1, message: Optional[str] = None):
        """
        更新进度
        
        参数：
            n: 增加的进度
            message: 附加消息
        """
        self.current += n
        percentage = (self.current / self.total) * 100 if self.total > 0 else 0
        filled = int(self.bar_length * self.current / self.total) if self.total > 0 else 0
        bar = '█' * filled + '░' * (self.bar_length - filled)
        
        # 计算已用时间
        elapsed = time.time() - self.start_time
        elapsed_str = self._format_time(elapsed)
        
        # 计算预估剩余时间
        if self.current > 0 and self.total > 0:
            rate = self.current / elapsed if elapsed > 0 else 0
            remaining = (self.total - self.current) / rate if rate > 0 else 0
            remaining_str = self._format_time(remaining)
            time_info = f"[{elapsed_str}<{remaining_str}]"
        else:
            time_info = f"[{elapsed_str}<--:--]"
        
        msg = f" - {message}" if message else ""
        
        # 使用 \r 回到行首，不换行
        sys.stdout.write(
            f"\r{self.desc}: [{bar}] {percentage:.1f}% "
            f"({self.current}/{self.total}) {time_info}{msg}"
        )
        sys.stdout.flush()
        
    def finish(self, message: str = "完成"):
        """
        完成显示
        
        参数：
            message: 完成消息
        """
        if self.current < self.total:
            self.update(self.total - self.current)
        
        elapsed = time.time() - self.start_time
        elapsed_str = self._format_time(elapsed)
        
        sys.stdout.write(f"\n{message} (用时: {elapsed_str})\n")
        sys.stdout.flush()
        
    def _format_time(self, seconds: float) -> str:
        """格式化时间"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}:{minutes:02d}"


class ProgressTracker:
    """进度追踪器"""
    
    def __init__(self, total: int, desc: str = "任务"):
        """
        初始化进度追踪器
        
        参数：
            total: 总任务数
            desc: 任务描述
        """
        self.info = ProgressInfo(total=total)
        self.desc = desc
        self.callbacks: List[Callable[[ProgressInfo], None]] = []
        
    def register_callback(self, callback: Callable[[ProgressInfo], None]):
        """注册进度回调函数"""
        self.callbacks.append(callback)
        
    def start(self, message: str = "开始"):
        """开始任务"""
        self.info.status = "running"
        self.info.start_time = datetime.now()
        self.info.message = message
        self._notify()
        
    def update(self, current: int, message: Optional[str] = None):
        """
        更新进度
        
        参数：
            current: 当前进度
            message: 进度消息
        """
        self.info.current = current
        if message:
            self.info.message = message
        self._notify()
        
    def increment(self, n: int = 1, message: Optional[str] = None):
        """
        增加进度
        
        参数：
            n: 增加的数量
            message: 进度消息
        """
        self.info.current += n
        if message:
            self.info.message = message
        self._notify()
        
    def complete(self, message: str = "完成"):
        """完成任务"""
        self.info.status = "completed"
        self.info.end_time = datetime.now()
        self.info.current = self.info.total
        self.info.message = message
        self._notify()
        
    def fail(self, error: str):
        """
        标记失败
        
        参数：
            error: 错误信息
        """
        self.info.status = "failed"
        self.info.end_time = datetime.now()
        self.info.error = error
        self.info.message = f"失败: {error}"
        self._notify()
        
    def _notify(self):
        """通知所有回调"""
        for callback in self.callbacks:
            try:
                callback(self.info)
            except Exception as e:
                print(f"进度回调执行失败: {e}")
                
    def get_percentage(self, decimals: int = 2) -> float:
        """
        获取进度百分比
        
        参数：
            decimals: 小数位数
            
        返回：
            float: 进度百分比
        """
        return round(self.info.percentage, decimals)


class MultiTaskProgressManager:
    """多任务进度管理器"""
    
    def __init__(self):
        """初始化多任务进度管理器"""
        self.tasks: Dict[str, ProgressTracker] = {}
        self.overall_progress = ProgressTracker(total=0, desc="总体进度")
        
    def add_task(self, task_id: str, total: int, desc: str = "任务") -> ProgressTracker:
        """
        添加任务
        
        参数：
            task_id: 任务ID
            total: 总任务数
            desc: 任务描述
            
        返回：
            ProgressTracker: 进度追踪器
        """
        tracker = ProgressTracker(total=total, desc=desc)
        self.tasks[task_id] = tracker
        self.overall_progress.info.total += total
        return tracker
        
    def get_task(self, task_id: str) -> Optional[ProgressTracker]:
        """
        获取任务进度追踪器
        
        参数：
            task_id: 任务ID
            
        返回：
            Optional[ProgressTracker]: 进度追踪器
        """
        return self.tasks.get(task_id)
        
    def update_overall(self):
        """更新总体进度"""
        total_current = sum(task.info.current for task in self.tasks.values())
        self.overall_progress.update(total_current)
        
    def get_overall_percentage(self, decimals: int = 2) -> float:
        """
        获取总体进度百分比
        
        参数：
            decimals: 小数位数
            
        返回：
            float: 总体进度百分比
        """
        return self.overall_progress.get_percentage(decimals)
        
    def print_summary(self):
        """打印进度摘要"""
        print("\n" + "=" * 60)
        print("任务进度摘要")
        print("=" * 60)
        
        for task_id, tracker in self.tasks.items():
            info = tracker.info
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌"
            }.get(info.status, "❓")
            
            print(f"{status_icon} {tracker.desc}: {info.current}/{info.total} "
                  f"({tracker.get_percentage(1)}%) - {info.status}")
            
        print("-" * 60)
        print(f"总体进度: {self.get_overall_percentage(1)}%")
        print("=" * 60)


def format_progress(percentage: float, decimals: int = 2) -> str:
    """
    格式化进度百分比
    
    参数：
        percentage: 百分比数值
        decimals: 小数位数
        
    返回：
        str: 格式化后的百分比字符串
    """
    return f"{percentage:.{decimals}f}%"


def create_progress_bar(total: int, desc: str = "进度") -> ConsoleProgressBar:
    """
    创建控制台进度条
    
    参数：
        total: 总任务数
        desc: 进度条描述
        
    返回：
        ConsoleProgressBar: 进度条实例
    """
    return ConsoleProgressBar(total=total, desc=desc)
