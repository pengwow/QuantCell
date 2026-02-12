#!/usr/bin/env python3
"""
性能测试基础类和数据模型
"""

import time
import psutil
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from datetime import datetime
import pandas as pd
import numpy as np


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    
    # 时间指标
    total_time_ms: float = 0.0
    data_load_time_ms: float = 0.0
    strategy_execution_time_ms: float = 0.0
    signal_generation_time_ms: float = 0.0
    
    # 资源使用指标
    memory_peak_mb: float = 0.0
    memory_avg_mb: float = 0.0
    cpu_avg_percent: float = 0.0
    cpu_peak_percent: float = 0.0
    
    # 交易指标
    total_trades: int = 0
    signals_generated: int = 0
    signal_latency_ms: float = 0.0
    
    # 异常处理
    exceptions_count: int = 0
    exception_handling_time_ms: float = 0.0
    
    # 元数据
    timestamp: datetime = field(default_factory=datetime.now)
    framework_name: str = ""
    data_points: int = 0
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'framework': self.framework_name,
            'timestamp': self.timestamp.isoformat(),
            'total_time_ms': self.total_time_ms,
            'data_load_time_ms': self.data_load_time_ms,
            'strategy_execution_time_ms': self.strategy_execution_time_ms,
            'signal_generation_time_ms': self.signal_generation_time_ms,
            'memory_peak_mb': self.memory_peak_mb,
            'memory_avg_mb': self.memory_avg_mb,
            'cpu_avg_percent': self.cpu_avg_percent,
            'cpu_peak_percent': self.cpu_peak_percent,
            'total_trades': self.total_trades,
            'signals_generated': self.signals_generated,
            'signal_latency_ms': self.signal_latency_ms,
            'exceptions_count': self.exceptions_count,
            'exception_handling_time_ms': self.exception_handling_time_ms,
            'data_points': self.data_points,
        }


class ResourceMonitor:
    """系统资源监控器"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.memory_samples: List[float] = []
        self.cpu_samples: List[float] = []
        self._monitoring = False
        
    def start(self):
        """开始监控"""
        self._monitoring = True
        self.memory_samples = []
        self.cpu_samples = []
        
    def sample(self):
        """采样当前资源使用情况"""
        if not self._monitoring:
            return
            
        # 内存使用 (MB)
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.memory_samples.append(memory_mb)
        
        # CPU使用率
        cpu_percent = self.process.cpu_percent()
        self.cpu_samples.append(cpu_percent)
        
    def stop(self) -> Dict[str, float]:
        """停止监控并返回统计结果"""
        self._monitoring = False
        
        if not self.memory_samples:
            return {
                'memory_peak_mb': 0.0,
                'memory_avg_mb': 0.0,
                'cpu_avg_percent': 0.0,
                'cpu_peak_percent': 0.0,
            }
            
        return {
            'memory_peak_mb': max(self.memory_samples),
            'memory_avg_mb': np.mean(self.memory_samples),
            'cpu_avg_percent': np.mean(self.cpu_samples) if self.cpu_samples else 0.0,
            'cpu_peak_percent': max(self.cpu_samples) if self.cpu_samples else 0.0,
        }


class Timer:
    """高精度计时器"""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.elapsed_ms: float = 0.0
        
    def start(self):
        """开始计时"""
        self.start_time = time.perf_counter()
        
    def stop(self) -> float:
        """停止计时并返回耗时（毫秒）"""
        if self.start_time is None:
            return 0.0
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        return self.elapsed_ms
        
    def __enter__(self):
        self.start()
        return self
        
    def __exit__(self, *args):
        self.stop()


class BasePerformanceTest(ABC):
    """性能测试基类"""
    
    def __init__(self, framework_name: str):
        self.framework_name = framework_name
        self.metrics = PerformanceMetrics(framework_name=framework_name)
        self.resource_monitor = ResourceMonitor()
        self.exceptions_count = 0
        self.exception_handling_time_ms = 0.0
        
    @abstractmethod
    def load_data(self, data_file: str) -> pd.DataFrame:
        """加载数据并返回DataFrame"""
        pass
        
    @abstractmethod
    def run_strategy(self, data: pd.DataFrame, strategy_params: Dict) -> Dict:
        """执行策略并返回结果"""
        pass
        
    def measure_performance(self, data_file: str, strategy_params: Dict) -> PerformanceMetrics:
        """
        执行完整的性能测试
        
        Args:
            data_file: 数据文件路径
            strategy_params: 策略参数
            
        Returns:
            PerformanceMetrics: 性能指标
        """
        # 重置指标
        self.metrics = PerformanceMetrics(framework_name=self.framework_name)
        self.exceptions_count = 0
        self.exception_handling_time_ms = 0.0
        
        # 开始资源监控
        self.resource_monitor.start()
        
        total_timer = Timer()
        total_timer.start()
        
        try:
            # 1. 数据加载阶段
            with Timer() as timer:
                data = self.load_data(data_file)
            self.metrics.data_load_time_ms = timer.elapsed_ms
            self.metrics.data_points = len(data)
            
            # 采样资源使用
            self.resource_monitor.sample()
            
            # 2. 策略执行阶段
            with Timer() as timer:
                result = self.run_strategy(data, strategy_params)
            self.metrics.strategy_execution_time_ms = timer.elapsed_ms
            
            # 采样资源使用
            self.resource_monitor.sample()
            
            # 3. 提取交易统计
            self.metrics.total_trades = result.get('total_trades', 0)
            self.metrics.signals_generated = result.get('signals_generated', 0)
            self.metrics.signal_latency_ms = result.get('signal_latency_ms', 0.0)
            
        except Exception as e:
            # 记录异常
            self.exceptions_count += 1
            with Timer() as timer:
                self.handle_exception(e)
            self.exception_handling_time_ms += timer.elapsed_ms
            
        finally:
            # 停止总计时
            self.metrics.total_time_ms = total_timer.stop()
            
            # 停止资源监控
            resource_stats = self.resource_monitor.stop()
            self.metrics.memory_peak_mb = resource_stats['memory_peak_mb']
            self.metrics.memory_avg_mb = resource_stats['memory_avg_mb']
            self.metrics.cpu_avg_percent = resource_stats['cpu_avg_percent']
            self.metrics.cpu_peak_percent = resource_stats['cpu_peak_percent']
            
            # 记录异常统计
            self.metrics.exceptions_count = self.exceptions_count
            self.metrics.exception_handling_time_ms = self.exception_handling_time_ms
            
        return self.metrics
        
    def handle_exception(self, exception: Exception):
        """处理异常，子类可以重写"""
        print(f"[{self.framework_name}] 异常: {exception}")
        
    def warmup(self, data_file: str, strategy_params: Dict):
        """预热运行，避免冷启动影响"""
        try:
            self.load_data(data_file)
            # 执行一次策略但不记录结果
        except:
            pass
