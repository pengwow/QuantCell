#!/usr/bin/env python3
"""
QuantCell 实盘交易模拟测试系统 - 主控制脚本

用于模拟QuantCell框架的实盘交易环境，支持历史数据回放、策略验证、实时监控。
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
import typer
from loguru import logger

from .config import load_config, create_default_config, SimulationConfig
from .data_loader import create_data_loader
from .data_pusher import create_data_pusher
from .connection import QuantCellClient
from .worker_manager import WorkerManager
from .monitor import create_monitor, MonitorCollector
from .exception_simulator import ExceptionSimulator
from .report_generator import create_report_generator, ReportData
from .models import SimulationState, SimulationMetrics

# 创建Typer应用
app = typer.Typer(
    name="live-simulation",
    help="QuantCell实盘交易模拟测试系统",
    add_completion=False,
)


class SimulationEngine:
    """模拟测试引擎"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.state = SimulationState.IDLE
        self.metrics = SimulationMetrics()
        
        # 初始化各模块
        self.data_loader = create_data_loader(config.data)
        self.data_pusher = create_data_pusher(config.push)
        self.quantcell_client = QuantCellClient(config.quantcell)
        self.worker_manager = WorkerManager()
        self.monitor = create_monitor(config.monitor)
        self.exception_simulator = ExceptionSimulator(config.exception_simulation)
        self.monitor_collector = MonitorCollector()
        self.report_generator = create_report_generator()
        
        # 注册处理器
        self._register_handlers()
        
    def _register_handlers(self):
        """注册各类处理器"""
        # 数据推送 -> QuantCell
        self.data_pusher.register_handler(self._on_market_data)
        
        # Worker事件
        self.worker_manager.register_status_handler(self._on_worker_status)
        self.worker_manager.register_signal_handler(self._on_trade_signal)
        self.worker_manager.register_order_handler(self._on_order)
        
        # QuantCell消息
        self.quantcell_client.register_handler("*", self._on_websocket_message)
        
    async def initialize(self):
        """初始化引擎"""
        logger.info("Initializing simulation engine...")
        
        # 初始化数据加载器
        await self.data_loader.initialize()
        
        # 加载数据
        data = await self.data_loader.load_all_data()
        self.data_pusher.load_multiple_data(data)
        self.metrics.total_data_points = sum(len(d) for d in data.values())
        
        # 注册Worker
        for i, worker_config in enumerate(self.config.workers):
            worker_id = f"worker_{i}"
            self.worker_manager.register_worker(worker_id, worker_config)
        
        self.state = SimulationState.IDLE
        logger.info("Simulation engine initialized")
        
    async def run(self):
        """运行模拟测试"""
        if self.state == SimulationState.RUNNING:
            logger.warning("Simulation is already running")
            return
            
        logger.info("Starting simulation...")
        self.state = SimulationState.RUNNING
        self.metrics.start_time = datetime.now()
        
        try:
            # 根据模式决定是否连接QuantCell
            if not self.config.standalone:
                # 连接QuantCell
                connected = await self.quantcell_client.connect()
                if not connected:
                    logger.warning("Failed to connect to QuantCell, running in standalone mode")
                    self.config.standalone = True
                else:
                    # 认证
                    await self.quantcell_client.authenticate()
            else:
                logger.info("Running in standalone mode (no QuantCell connection)")
                
            # 启动Worker
            for worker_id in self.worker_manager._workers.keys():
                await self.worker_manager.start_worker(worker_id)
                
            # 启动监控
            if self.config.monitor.enabled:
                await self.monitor.start()
                
            # 启动异常模拟
            if self.config.exception_simulation.enabled:
                await self.exception_simulator.start()
                
            # 启动数据推送
            await self.data_pusher.start()
            
            # 等待数据推送完成或超时
            await self._wait_for_completion()
            
        except Exception as e:
            logger.error(f"Simulation error: {e}")
            self.state = SimulationState.ERROR
            raise
        finally:
            await self.stop()
            
    async def stop(self):
        """停止模拟测试"""
        if self.state == SimulationState.STOPPED:
            return
            
        logger.info("Stopping simulation...")
        self.state = SimulationState.STOPPING
        
        # 停止各组件
        await self.data_pusher.stop()
        await self.exception_simulator.stop()
        await self.monitor.stop()
        self.worker_manager.stop_all_workers()
        
        # 仅在非独立模式下断开连接
        if not self.config.standalone:
            await self.quantcell_client.disconnect()
        
        self.metrics.end_time = datetime.now()
        self.state = SimulationState.STOPPED
        
        logger.info("Simulation stopped")
        
    async def pause(self):
        """暂停模拟测试"""
        if self.state == SimulationState.RUNNING:
            await self.data_pusher.pause()
            self.state = SimulationState.PAUSED
            logger.info("Simulation paused")
            
    async def resume(self):
        """恢复模拟测试"""
        if self.state == SimulationState.PAUSED:
            await self.data_pusher.resume()
            self.state = SimulationState.RUNNING
            logger.info("Simulation resumed")
            
    async def _wait_for_completion(self):
        """等待测试完成"""
        max_duration = self.config.duration_hours * 3600  # 转换为秒
        start_time = asyncio.get_event_loop().time()
        
        while self.state == SimulationState.RUNNING:
            # 检查是否超时
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= max_duration:
                logger.info(f"Simulation reached max duration ({self.config.duration_hours} hours)")
                break
                
            # 检查数据推送是否完成
            if self.data_pusher.get_state() == SimulationState.COMPLETED:
                logger.info("Data pushing completed")
                break
                
            await asyncio.sleep(1.0)
            
    def _on_market_data(self, message):
        """处理市场数据"""
        # 仅在非独立模式下发送到QuantCell
        if not self.config.standalone and self.quantcell_client.is_connected:
            asyncio.create_task(self.quantcell_client.send_market_data(message))
        
        # 分发给Workers（独立模式和连接模式都执行）
        for worker_id in self.worker_manager.get_running_workers():
            asyncio.create_task(
                self.worker_manager.handle_market_data(worker_id, message.to_dict())
            )
            
    def _on_worker_status(self, status):
        """处理Worker状态更新"""
        self.monitor_collector.on_worker_status(status)
        
    def _on_trade_signal(self, signal):
        """处理交易信号"""
        self.monitor_collector.on_signal(signal)
        self.metrics.total_signals += 1
        
    def _on_order(self, order):
        """处理订单"""
        self.monitor_collector.on_order(order)
        self.metrics.total_orders += 1
        if order.status.value == "filled":
            self.metrics.filled_orders += 1
            
    def _on_websocket_message(self, message):
        """处理WebSocket消息"""
        # 这里可以处理从QuantCell返回的消息
        pass
        
    def generate_report(self, output_dir: str) -> list:
        """生成测试报告"""
        report_data = ReportData(
            report_name=self.config.name,
            start_time=self.metrics.start_time,
            end_time=self.metrics.end_time,
            config=self.config.dict(),
            metrics=self.metrics,
            signals=self.monitor_collector._signals,
            orders=self.monitor_collector._orders,
            extra_data={
                "worker_stats": self.worker_manager.get_worker_stats(),
                "exception_summary": self.exception_simulator.get_summary(),
            }
        )
        
        return self.report_generator.generate_report(report_data, output_dir)


# 全局引擎实例
_engine: Optional[SimulationEngine] = None


def _signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"Received signal {signum}")
    if _engine:
        asyncio.create_task(_engine.stop())


@app.command()
def run(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    data_path: Optional[str] = typer.Option(None, "--data-path", "-d", help="数据文件路径"),
    strategy_path: Optional[str] = typer.Option(None, "--strategy", "-s", help="策略文件路径"),
    speed: float = typer.Option(1.0, "--speed", help="数据推送速度倍率"),
    duration: float = typer.Option(8.0, "--duration", help="测试持续时间（小时）"),
    output_dir: str = typer.Option("./reports", "--output", "-o", help="报告输出目录"),
):
    """运行模拟测试"""
    global _engine
    
    # 加载配置
    if config:
        simulation_config = load_config(config)
    else:
        simulation_config = SimulationConfig()
        
    # 命令行参数覆盖配置
    if data_path:
        simulation_config.data.file_path = data_path
    if strategy_path:
        if simulation_config.workers:
            simulation_config.workers[0].strategy_path = strategy_path
    if speed:
        simulation_config.push.speed = speed
    if duration:
        simulation_config.duration_hours = duration
        
    # 创建引擎
    _engine = SimulationEngine(simulation_config)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    async def main():
        try:
            await _engine.initialize()
            await _engine.run()
            
            # 生成报告
            logger.info(f"Generating report to {output_dir}")
            report_files = _engine.generate_report(output_dir)
            for f in report_files:
                logger.info(f"Report generated: {f}")
                
        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            raise
            
    asyncio.run(main())


@app.command()
def create_config(
    output: str = typer.Argument(..., help="输出配置文件路径"),
):
    """创建默认配置文件"""
    create_default_config(output)
    typer.echo(f"Default config created at: {output}")


@app.command()
def validate(
    config: str = typer.Argument(..., help="配置文件路径"),
):
    """验证配置文件"""
    try:
        simulation_config = load_config(config)
        typer.echo("✓ Configuration is valid")
        typer.echo(f"  Name: {simulation_config.name}")
        typer.echo(f"  Data source: {simulation_config.data.source_type}")
        typer.echo(f"  Push speed: {simulation_config.push.speed}x")
        typer.echo(f"  Workers: {len(simulation_config.workers)}")
    except Exception as e:
        typer.echo(f"✗ Configuration error: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
