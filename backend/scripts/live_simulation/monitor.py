"""
监控脚本

实时监控模拟交易过程中的关键指标。
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger

from .models import (
    WorkerStatus, OrderInfo, PositionInfo, TradeSignal,
    SimulationMetrics, SimulationState
)
from .config import MonitorConfig


@dataclass
class MonitorMetrics:
    """监控指标"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 数据推送指标
    data_points_pushed: int = 0
    push_progress_percent: float = 0.0
    push_speed: float = 1.0
    
    # Worker指标
    active_workers: int = 0
    total_workers: int = 0
    messages_processed: int = 0
    worker_errors: int = 0
    
    # 交易指标
    total_signals: int = 0
    total_orders: int = 0
    filled_orders: int = 0
    open_positions: int = 0
    
    # 盈亏指标
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # 连接指标
    ws_connected: bool = False
    ws_messages_sent: int = 0
    ws_messages_received: int = 0


class BaseMonitor(ABC):
    """监控基类"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._metrics_history: List[MonitorMetrics] = []
        
    @abstractmethod
    async def _update_display(self, metrics: MonitorMetrics):
        """更新显示"""
        pass
        
    @abstractmethod
    async def _initialize(self):
        """初始化"""
        pass
        
    @abstractmethod
    async def _cleanup(self):
        """清理"""
        pass
        
    async def start(self):
        """启动监控"""
        if self._running:
            return
            
        self._running = True
        await self._initialize()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Monitor started")
        
    async def stop(self):
        """停止监控"""
        if not self._running:
            return
            
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
        await self._cleanup()
        logger.info("Monitor stopped")
        
    async def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                # 这里应该收集实际的指标
                metrics = MonitorMetrics()
                
                # 保存历史
                self._metrics_history.append(metrics)
                if len(self._metrics_history) > self.config.metrics_history_size:
                    self._metrics_history.pop(0)
                    
                # 更新显示
                await self._update_display(metrics)
                
                # 等待下一次更新
                await asyncio.sleep(self.config.update_interval_ms / 1000.0)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(1.0)
                
    def update_metrics(self, metrics: MonitorMetrics):
        """更新指标（供外部调用）"""
        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self.config.metrics_history_size:
            self._metrics_history.pop(0)
            
    def get_metrics_history(self) -> List[MonitorMetrics]:
        """获取指标历史"""
        return self._metrics_history.copy()


class ConsoleMonitor(BaseMonitor):
    """控制台监控器"""
    
    def __init__(self, config: MonitorConfig):
        super().__init__(config)
        self._last_lines = 0
        
    async def _initialize(self):
        """初始化"""
        pass
        
    async def _cleanup(self):
        """清理"""
        pass
        
    async def _update_display(self, metrics: MonitorMetrics):
        """更新控制台显示"""
        if not self.config.console_output:
            return
            
        # 构建显示内容
        lines = []
        lines.append("=" * 80)
        lines.append(f"QuantCell 模拟交易监控 - {metrics.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        
        # 数据推送
        lines.append("\n[数据推送]")
        lines.append(f"  已推送: {metrics.data_points_pushed} 条")
        lines.append(f"  进度: {metrics.push_progress_percent:.2f}%")
        lines.append(f"  速度: {metrics.push_speed}x")
        
        # Worker状态
        lines.append("\n[Worker状态]")
        lines.append(f"  活跃/总数: {metrics.active_workers}/{metrics.total_workers}")
        lines.append(f"  消息处理: {metrics.messages_processed} 条")
        lines.append(f"  错误数: {metrics.worker_errors}")
        
        # 交易统计
        lines.append("\n[交易统计]")
        lines.append(f"  信号数: {metrics.total_signals}")
        lines.append(f"  订单数: {metrics.total_orders}")
        lines.append(f"  成交: {metrics.filled_orders}")
        lines.append(f"  持仓: {metrics.open_positions}")
        
        # 盈亏
        lines.append("\n[盈亏情况]")
        lines.append(f"  总盈亏: {metrics.total_pnl:+.2f}")
        lines.append(f"  已实现: {metrics.realized_pnl:+.2f}")
        lines.append(f"  未实现: {metrics.unrealized_pnl:+.2f}")
        
        # 连接状态
        lines.append("\n[连接状态]")
        lines.append(f"  WebSocket: {'已连接' if metrics.ws_connected else '未连接'}")
        lines.append(f"  发送: {metrics.ws_messages_sent} 条")
        lines.append(f"  接收: {metrics.ws_messages_received} 条")
        
        lines.append("\n" + "=" * 80)
        
        # 清屏并输出
        output = "\n".join(lines)
        print(output)


class MonitorCollector:
    """监控数据收集器"""
    
    def __init__(self):
        self._signals: List[TradeSignal] = []
        self._orders: List[OrderInfo] = []
        self._positions: Dict[str, PositionInfo] = {}
        self._worker_status: Dict[str, WorkerStatus] = {}
        
        # 统计
        self._total_signals = 0
        self._total_orders = 0
        self._filled_orders = 0
        self._total_pnl = 0.0
        
    def on_signal(self, signal: TradeSignal):
        """处理交易信号"""
        self._signals.append(signal)
        self._total_signals += 1
        logger.info(f"Signal: {signal.signal_type.value} {signal.symbol} @ {signal.price}")
        
    def on_order(self, order: OrderInfo):
        """处理订单"""
        self._orders.append(order)
        self._total_orders += 1
        
        if order.status.value == "filled":
            self._filled_orders += 1
            
        logger.info(f"Order: {order.side.value} {order.symbol} {order.quantity} @ {order.avg_price}")
        
    def on_position_update(self, position: PositionInfo):
        """处理持仓更新"""
        self._positions[position.symbol] = position
        
    def on_worker_status(self, status: WorkerStatus):
        """处理Worker状态更新"""
        self._worker_status[status.worker_id] = status
        
    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        return {
            "total_signals": self._total_signals,
            "total_orders": self._total_orders,
            "filled_orders": self._filled_orders,
            "open_positions": len(self._positions),
            "active_workers": sum(1 for s in self._worker_status.values() if s.state.value == "running"),
            "total_workers": len(self._worker_status),
        }
        
    def get_recent_signals(self, n: int = 10) -> List[TradeSignal]:
        """获取最近的交易信号"""
        return self._signals[-n:]
        
    def get_recent_orders(self, n: int = 10) -> List[OrderInfo]:
        """获取最近的订单"""
        return self._orders[-n:]
        
    def get_positions(self) -> Dict[str, PositionInfo]:
        """获取当前持仓"""
        return self._positions.copy()
        
    def clear(self):
        """清除所有数据"""
        self._signals.clear()
        self._orders.clear()
        self._positions.clear()
        self._worker_status.clear()
        self._total_signals = 0
        self._total_orders = 0
        self._filled_orders = 0
        self._total_pnl = 0.0


def create_monitor(config: MonitorConfig) -> BaseMonitor:
    """创建监控器"""
    if config.web_interface:
        # 如果需要Web界面，可以实现WebMonitor
        # 暂时返回控制台监控器
        return ConsoleMonitor(config)
    return ConsoleMonitor(config)
