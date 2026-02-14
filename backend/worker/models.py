# -*- coding: utf-8 -*-
"""
Worker数据库模型定义
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, 
    ForeignKey, Enum, Index, UniqueConstraint, func
)
from sqlalchemy.orm import relationship

from collector.db.database import Base


class Worker(Base):
    """Worker基础模型"""
    __tablename__ = "workers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Worker状态: stopped, running, paused, error, starting, stopping
    status = Column(String(20), default='stopped', index=True)
    
    # 策略关联
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=True)
    strategy = relationship("Strategy", back_populates="workers")
    
    # 交易配置
    exchange = Column(String(50), nullable=False, default='binance')
    symbol = Column(String(50), nullable=False, default='BTCUSDT')
    timeframe = Column(String(10), nullable=False, default='1h')
    market_type = Column(String(20), default='spot')  # spot, future
    
    # 交易模式: paper(模拟), live(实盘)
    trading_mode = Column(String(10), default='paper')
    
    # 资源配置
    cpu_limit = Column(Integer, default=1)  # CPU核心数
    memory_limit = Column(Integer, default=512)  # 内存限制(MB)
    
    # 运行环境变量(JSON格式)
    env_vars = Column(Text, default='{}')
    
    # Worker配置(JSON格式)
    config = Column(Text, default='{}')
    
    # 进程信息
    pid = Column(Integer, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    
    # 关联关系
    logs = relationship("WorkerLog", back_populates="worker", cascade="all, delete-orphan")
    performance = relationship("WorkerPerformance", back_populates="worker", cascade="all, delete-orphan")
    risk_config = relationship("WorkerRiskControl", back_populates="worker", uselist=False, cascade="all, delete-orphan")
    capital_config = relationship("WorkerCapital", back_populates="worker", uselist=False, cascade="all, delete-orphan")
    parameters = relationship("WorkerParameter", back_populates="worker", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('name', name='unique_worker_name'),
        Index('idx_worker_status', 'status'),
        Index('idx_worker_strategy', 'strategy_id'),
    )
    
    def get_env_vars_dict(self) -> Dict[str, str]:
        """获取环境变量字典"""
        try:
            return json.loads(self.env_vars) if self.env_vars else {}
        except json.JSONDecodeError:
            return {}
    
    def set_env_vars_dict(self, env_vars: Dict[str, str]):
        """设置环境变量字典"""
        self.env_vars = json.dumps(env_vars)
    
    def get_config_dict(self) -> Dict[str, Any]:
        """获取配置字典"""
        try:
            return json.loads(self.config) if self.config else {}
        except json.JSONDecodeError:
            return {}
    
    def set_config_dict(self, config: Dict[str, Any]):
        """设置配置字典"""
        self.config = json.dumps(config)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'strategy_id': self.strategy_id,
            'exchange': self.exchange,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'market_type': self.market_type,
            'trading_mode': self.trading_mode,
            'cpu_limit': self.cpu_limit,
            'memory_limit': self.memory_limit,
            'pid': self.pid,
            'config': self.get_config_dict(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'stopped_at': self.stopped_at.isoformat() if self.stopped_at else None,
        }


class WorkerLog(Base):
    """Worker日志模型"""
    __tablename__ = "worker_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, index=True)
    worker = relationship("Worker", back_populates="logs")
    
    # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
    level = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=False)
    source = Column(String(100), nullable=True)  # 日志来源
    
    # 时间戳
    timestamp = Column(DateTime, default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_worker_log', 'worker_id', 'timestamp'),
        Index('idx_worker_log_level', 'worker_id', 'level'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'level': self.level,
            'message': self.message,
            'source': self.source,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


class WorkerPerformance(Base):
    """Worker绩效模型"""
    __tablename__ = "worker_performance"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, index=True)
    worker = relationship("Worker", back_populates="performance")
    
    # 交易统计
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    # 收益统计
    total_profit = Column(Float, default=0.0)
    total_loss = Column(Float, default=0.0)
    gross_profit = Column(Float, default=0.0)  # 毛利润
    net_profit = Column(Float, default=0.0)  # 净利润
    
    # 风险指标
    max_drawdown = Column(Float, default=0.0)  # 最大回撤
    max_drawdown_pct = Column(Float, default=0.0)  # 最大回撤百分比
    sharpe_ratio = Column(Float, default=0.0)  # 夏普比率
    sortino_ratio = Column(Float, default=0.0)  # 索提诺比率
    calmar_ratio = Column(Float, default=0.0)  # 卡尔马比率
    
    # 其他指标
    win_rate = Column(Float, default=0.0)  # 胜率
    profit_factor = Column(Float, default=0.0)  # 盈亏比
    avg_profit = Column(Float, default=0.0)  # 平均盈利
    avg_loss = Column(Float, default=0.0)  # 平均亏损
    
    # 日期
    date = Column(DateTime, nullable=False, index=True)
    
    __table_args__ = (
        UniqueConstraint('worker_id', 'date', name='unique_worker_performance_date'),
        Index('idx_worker_performance_date', 'worker_id', 'date'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_profit': self.total_profit,
            'total_loss': self.total_loss,
            'gross_profit': self.gross_profit,
            'net_profit': self.net_profit,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown_pct,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'avg_profit': self.avg_profit,
            'avg_loss': self.avg_loss,
            'date': self.date.isoformat() if self.date else None,
        }


class WorkerRiskControl(Base):
    """Worker风险控制模型"""
    __tablename__ = "worker_risk_control"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, unique=True)
    worker = relationship("Worker", back_populates="risk_config")
    
    # 仓位控制
    max_position_size = Column(Float, default=1.0)  # 最大仓位(手数或金额)
    max_position_pct = Column(Float, default=0.1)  # 最大仓位比例(相对于资金)
    max_open_positions = Column(Integer, default=5)  # 最大持仓数量
    
    # 止损设置
    stop_loss_pct = Column(Float, default=0.02)  # 止损百分比
    stop_loss_amount = Column(Float, nullable=True)  # 止损金额
    trailing_stop_pct = Column(Float, nullable=True)  # 追踪止损百分比
    
    # 止盈设置
    take_profit_pct = Column(Float, default=0.05)  # 止盈百分比
    take_profit_amount = Column(Float, nullable=True)  # 止盈金额
    
    # 日度限制
    daily_loss_limit = Column(Float, default=0.05)  # 日度最大亏损比例
    daily_loss_amount = Column(Float, nullable=True)  # 日度最大亏损金额
    daily_trade_limit = Column(Integer, default=50)  # 日度最大交易次数
    
    # 其他风控
    max_slippage_pct = Column(Float, default=0.001)  # 最大滑点
    max_spread_pct = Column(Float, default=0.005)  # 最大点差
    
    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'max_position_size': self.max_position_size,
            'max_position_pct': self.max_position_pct,
            'max_open_positions': self.max_open_positions,
            'stop_loss_pct': self.stop_loss_pct,
            'stop_loss_amount': self.stop_loss_amount,
            'trailing_stop_pct': self.trailing_stop_pct,
            'take_profit_pct': self.take_profit_pct,
            'take_profit_amount': self.take_profit_amount,
            'daily_loss_limit': self.daily_loss_limit,
            'daily_loss_amount': self.daily_loss_amount,
            'daily_trade_limit': self.daily_trade_limit,
            'max_slippage_pct': self.max_slippage_pct,
            'max_spread_pct': self.max_spread_pct,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkerCapital(Base):
    """Worker资金配置模型"""
    __tablename__ = "worker_capital"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, unique=True)
    worker = relationship("Worker", back_populates="capital_config")
    
    # 资金配置
    initial_capital = Column(Float, default=100000.0)  # 初始资金
    current_capital = Column(Float, default=100000.0)  # 当前资金
    available_capital = Column(Float, default=100000.0)  # 可用资金
    frozen_capital = Column(Float, default=0.0)  # 冻结资金
    margin_used = Column(Float, default=0.0)  # 已用保证金
    margin_ratio = Column(Float, default=0.0)  # 保证金比例
    
    # 杠杆设置
    leverage = Column(Float, default=1.0)  # 杠杆倍数
    max_leverage = Column(Float, default=10.0)  # 最大杠杆
    
    # 币种
    currency = Column(String(10), default='USDT')
    
    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'available_capital': self.available_capital,
            'frozen_capital': self.frozen_capital,
            'margin_used': self.margin_used,
            'margin_ratio': self.margin_ratio,
            'leverage': self.leverage,
            'max_leverage': self.max_leverage,
            'currency': self.currency,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkerParameter(Base):
    """Worker策略参数模型"""
    __tablename__ = "worker_parameters"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, index=True)
    worker = relationship("Worker", back_populates="parameters")
    
    # 参数信息
    param_name = Column(String(100), nullable=False)
    param_value = Column(Text, nullable=False)
    param_type = Column(String(20), default='string')  # string, int, float, bool, json
    description = Column(Text, nullable=True)
    
    # 参数范围(用于UI展示和验证)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    options = Column(Text, nullable=True)  # JSON数组,用于枚举类型
    
    # 是否可以运行时修改
    editable = Column(Boolean, default=True)
    
    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('worker_id', 'param_name', name='unique_worker_parameter'),
        Index('idx_worker_parameter', 'worker_id', 'param_name'),
    )
    
    def get_value(self) -> Any:
        """根据类型解析参数值"""
        try:
            if self.param_type == 'int':
                return int(self.param_value)
            elif self.param_type == 'float':
                return float(self.param_value)
            elif self.param_type == 'bool':
                return self.param_value.lower() in ('true', '1', 'yes', 'on')
            elif self.param_type == 'json':
                return json.loads(self.param_value)
            else:
                return self.param_value
        except (ValueError, json.JSONDecodeError):
            return self.param_value
    
    def set_value(self, value: Any):
        """设置参数值并自动推断类型"""
        if isinstance(value, bool):
            self.param_type = 'bool'
            self.param_value = str(value).lower()
        elif isinstance(value, int):
            self.param_type = 'int'
            self.param_value = str(value)
        elif isinstance(value, float):
            self.param_type = 'float'
            self.param_value = str(value)
        elif isinstance(value, (dict, list)):
            self.param_type = 'json'
            self.param_value = json.dumps(value)
        else:
            self.param_type = 'string'
            self.param_value = str(value)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'param_name': self.param_name,
            'param_value': self.get_value(),
            'param_type': self.param_type,
            'description': self.description,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'options': json.loads(self.options) if self.options else None,
            'editable': self.editable,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkerStatusHistory(Base):
    """Worker状态历史记录"""
    __tablename__ = "worker_status_history"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, index=True)
    
    # 状态变更
    old_status = Column(String(20), nullable=False)
    new_status = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)  # 状态变更原因
    
    # 时间戳
    timestamp = Column(DateTime, default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_worker_status_history', 'worker_id', 'timestamp'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'old_status': self.old_status,
            'new_status': self.new_status,
            'reason': self.reason,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


class WorkerMetric(Base):
    """Worker性能指标模型"""
    __tablename__ = "worker_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, index=True)
    
    # CPU和内存指标
    cpu_usage = Column(Float, default=0.0)  # CPU使用率(%)
    memory_usage = Column(Float, default=0.0)  # 内存使用率(%)
    memory_used_mb = Column(Float, default=0.0)  # 已用内存(MB)
    memory_total_mb = Column(Float, default=0.0)  # 总内存(MB)
    
    # 网络指标
    network_in = Column(Integer, default=0)  # 网络流入字节数
    network_out = Column(Integer, default=0)  # 网络流出字节数
    
    # 任务指标
    active_tasks = Column(Integer, default=0)  # 活跃任务数
    queued_tasks = Column(Integer, default=0)  # 队列中任务数
    completed_tasks = Column(Integer, default=0)  # 已完成任务数
    failed_tasks = Column(Integer, default=0)  # 失败任务数
    
    # 时间戳
    timestamp = Column(DateTime, default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_worker_metric_time', 'worker_id', 'timestamp'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'memory_used_mb': self.memory_used_mb,
            'memory_total_mb': self.memory_total_mb,
            'network_in': self.network_in,
            'network_out': self.network_out,
            'active_tasks': self.active_tasks,
            'queued_tasks': self.queued_tasks,
            'completed_tasks': self.completed_tasks,
            'failed_tasks': self.failed_tasks,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


class WorkerTrade(Base):
    """Worker交易记录模型"""
    __tablename__ = "worker_trades"
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=False, index=True)
    
    # 交易信息
    trade_id = Column(String(100), unique=True, nullable=False)
    symbol = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)  # buy, sell
    order_type = Column(String(20), nullable=False)  # market, limit, stop
    
    # 交易数量
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)  # quantity * price
    
    # 费用
    fee = Column(Float, default=0.0)
    fee_currency = Column(String(10), default='USDT')
    
    # 盈亏
    realized_pnl = Column(Float, nullable=True)  # 已实现盈亏
    realized_pnl_pct = Column(Float, nullable=True)  # 已实现盈亏百分比
    
    # 时间戳
    entry_time = Column(DateTime, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        Index('idx_worker_trade_symbol', 'worker_id', 'symbol'),
        Index('idx_worker_trade_time', 'worker_id', 'created_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type,
            'quantity': self.quantity,
            'price': self.price,
            'amount': self.amount,
            'fee': self.fee,
            'fee_currency': self.fee_currency,
            'realized_pnl': self.realized_pnl,
            'realized_pnl_pct': self.realized_pnl_pct,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
