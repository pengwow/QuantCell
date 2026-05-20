"""
Worker API数据模型定义

定义Pydantic请求和响应模型
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, model_validator


class SymbolsConfig(BaseModel):
    """交易标的配置"""
    type: str = Field(default="symbols", description="配置类型: symbols-直接货币对, pool-自选组")
    symbols: List[str] = Field(default_factory=list, description="货币对列表")
    pool_id: Optional[int] = Field(None, description="自选组ID")
    pool_name: Optional[str] = Field(None, description="自选组名称")


class TradingConfig(BaseModel):
    """交易配置"""
    exchange: str = Field(default="binance", description="交易所")
    symbols_config: SymbolsConfig = Field(default_factory=lambda: SymbolsConfig(type="symbols", symbols=[], pool_id=None, pool_name=None), description="交易标的配置")
    timeframe: str = Field(default="1h", description="时间周期")
    market_type: str = Field(default="spot", description="市场类型: spot/future")
    trading_mode: str = Field(default="paper", description="交易模式: paper/live")


class WorkerBase(BaseModel):
    """Worker基础模型"""
    name: str = Field(..., description="Worker名称", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Worker描述")
    strategy_id: Optional[int] = Field(default=None, description="关联策略ID")


class WorkerCreate(WorkerBase):
    """创建Worker请求模型"""
    # 策略相关字段
    strategy_file_name: Optional[str] = Field(
        default=None,
        description="策略文件名称（如 grid_order_validation.py），当 strategy_id 在数据库中找不到时使用"
    )
    strategy_name: Optional[str] = Field(
        default=None,
        description="策略名称（冗余存储，用于在 strategy_id 失效时通过名称查找策略）"
    )

    # 交易配置（新格式）
    trading_config: Optional[TradingConfig] = Field(None, description="交易配置")
    # 兼容旧版本的字段
    exchange: Optional[str] = Field(default="binance", description="交易所")
    symbols: Optional[List[str]] = Field(default=None, description="交易对列表")
    symbol: Optional[str] = Field(default=None, description="交易对（单数形式，兼容前端）")  # 前端发送的是单数形式
    timeframe: Optional[str] = Field(default="1h", description="时间周期")
    market_type: Optional[str] = Field(default="spot", description="市场类型: spot/future")
    trading_mode: Optional[str] = Field(default="paper", description="交易模式: paper/live")
    # 其他配置
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="环境变量")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Worker配置")

    @model_validator(mode='after')
    def validate_symbols(self):
        """验证交易对配置 - 兼容旧版扁平字段与新版 trading_config"""
        return self


class WorkerUpdate(BaseModel):
    """更新Worker请求模型"""
    name: Optional[str] = Field(None, description="Worker名称")
    description: Optional[str] = Field(None, description="Worker描述")
    strategy_id: Optional[int] = Field(None, description="关联策略ID")
    strategy_file_name: Optional[str] = Field(
        None,
        description="策略文件名称"
    )
    strategy_name: Optional[str] = Field(
        None,
        description="策略名称（冗余存储，用于在 strategy_id 失效时通过名称查找策略）"
    )
    # 交易配置（新格式）
    trading_config: Optional[TradingConfig] = Field(None, description="交易配置")
    # 兼容旧版本的字段
    exchange: Optional[str] = Field(None, description="交易所")
    symbols: Optional[List[str]] = Field(None, description="交易对列表")
    timeframe: Optional[str] = Field(None, description="时间周期")
    trading_mode: Optional[str] = Field(None, description="交易模式")
    config: Optional[Dict[str, Any]] = Field(None, description="Worker配置")


class WorkerConfigUpdate(BaseModel):
    """部分更新Worker配置"""
    config: Dict[str, Any] = Field(..., description="更新的配置项")


class StrategyInfo(BaseModel):
    """策略信息"""
    id: int = Field(..., description="策略ID")
    name: str = Field(..., description="策略名称")
    description: Optional[str] = Field(None, description="策略描述")
    strategy_type: str = Field(default="default", description="策略类型: default")
    version: str = Field(default="1.0.0", description="策略版本")


class WorkerResponse(WorkerBase):
    """Worker响应模型"""
    id: int = Field(..., description="Worker ID")
    status: str = Field(..., description="Worker状态")
    pid: Optional[int] = Field(None, description="进程ID")
    # 交易配置（新格式）
    trading_config: Optional[TradingConfig] = Field(None, description="交易配置")
    # 兼容旧版本字段
    exchange: Optional[str] = Field(None, description="交易所")
    symbols: Optional[List[str]] = Field(None, description="交易对列表")
    timeframe: Optional[str] = Field(None, description="时间周期")
    market_type: Optional[str] = Field(None, description="市场类型")
    trading_mode: Optional[str] = Field(None, description="交易模式")
    config: Optional[Dict[str, Any]] = Field(None, description="Worker配置")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    started_at: Optional[datetime] = Field(None, description="启动时间")
    stopped_at: Optional[datetime] = Field(None, description="停止时间")
    total_profit: Optional[float] = Field(None, description="总收益")
    strategy_info: Optional[StrategyInfo] = Field(None, description="关联策略信息")

    class Config:
        from_attributes = True


class WorkerListResponse(BaseModel):
    """Worker列表响应"""
    items: List[WorkerResponse] = Field(..., description="Worker列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页")
    page_size: int = Field(..., description="每页大小")


class WorkerCommand(BaseModel):
    """Worker控制命令"""
    command: str = Field(..., description="命令: start/stop/pause/resume/restart")
    params: Optional[Dict[str, Any]] = Field(None, description="命令参数")


class WorkerStatusResponse(BaseModel):
    """Worker状态响应"""
    worker_id: int = Field(..., description="Worker ID")
    status: str = Field(..., description="当前状态")
    pid: Optional[int] = Field(None, description="进程ID")
    uptime: Optional[float] = Field(None, description="运行时间(秒)")
    last_heartbeat: Optional[datetime] = Field(None, description="最后心跳时间")
    is_healthy: bool = Field(..., description="是否健康")


class WorkerMetrics(BaseModel):
    """Worker性能指标"""
    worker_id: int = Field(..., description="Worker ID")
    network_in: int = Field(..., description="网络流入字节数")
    network_out: int = Field(..., description="网络流出字节数")
    active_tasks: int = Field(..., description="活跃任务数")
    timestamp: datetime = Field(..., description="采集时间")


class WorkerLogEntry(BaseModel):
    """Worker日志条目"""
    id: int = Field(..., description="日志ID")
    worker_id: int = Field(..., description="Worker ID")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志内容")
    source: Optional[str] = Field(None, description="日志来源")
    timestamp: datetime = Field(..., description="日志时间")

    class Config:
        from_attributes = True


class WorkerPerformance(BaseModel):
    """Worker绩效数据"""
    worker_id: int = Field(..., description="Worker ID")
    total_trades: int = Field(..., description="总交易次数")
    winning_trades: int = Field(..., description="盈利交易次数")
    losing_trades: int = Field(..., description="亏损交易次数")
    win_rate: float = Field(..., description="胜率(%)")
    total_profit: float = Field(..., description="总盈利")
    total_loss: float = Field(..., description="总亏损")
    net_profit: float = Field(..., description="净利润")
    max_drawdown: float = Field(..., description="最大回撤")
    sharpe_ratio: float = Field(..., description="夏普比率")
    date: datetime = Field(..., description="日期")

    class Config:
        from_attributes = True


class StrategyDeployRequest(BaseModel):
    """策略部署请求"""
    strategy_id: int = Field(..., description="策略ID")
    parameters: Optional[Dict[str, Any]] = Field(None, description="策略参数")
    auto_start: bool = Field(default=False, description="是否自动启动")


class StrategyParameter(BaseModel):
    """策略参数"""
    param_name: str = Field(..., description="参数名")
    param_value: Any = Field(..., description="参数值")
    param_type: str = Field(..., description="参数类型")
    description: Optional[str] = Field(None, description="参数描述")
    min_value: Optional[float] = Field(None, description="最小值")
    max_value: Optional[float] = Field(None, description="最大值")
    editable: bool = Field(default=True, description="是否可编辑")


class StrategyParameterUpdate(BaseModel):
    """策略参数更新"""
    parameters: Dict[str, Any] = Field(..., description="参数键值对")


class PositionInfo(BaseModel):
    """持仓信息"""
    symbol: str = Field(..., description="交易对")
    side: str = Field(..., description="方向: long/short")
    quantity: float = Field(..., description="持仓数量")
    entry_price: float = Field(..., description="入场价格")
    current_price: float = Field(..., description="当前价格")
    unrealized_pnl: float = Field(..., description="未实现盈亏")
    unrealized_pnl_pct: float = Field(..., description="未实现盈亏百分比")
    timestamp: datetime = Field(..., description="时间")


class OrderInfo(BaseModel):
    """订单信息"""
    order_id: str = Field(..., description="订单ID")
    symbol: str = Field(..., description="交易对")
    side: str = Field(..., description="方向: buy/sell")
    order_type: str = Field(..., description="订单类型")
    quantity: float = Field(..., description="数量")
    price: Optional[float] = Field(None, description="价格")
    status: str = Field(..., description="订单状态")
    filled_quantity: float = Field(..., description="已成交数量")
    created_at: datetime = Field(..., description="创建时间")


class BatchOperationRequest(BaseModel):
    """批量操作请求"""
    worker_ids: List[int] = Field(..., description="Worker ID列表")
    operation: str = Field(..., description="操作: start/stop/restart")


class BatchOperationResponse(BaseModel):
    """批量操作响应"""
    success: List[int] = Field(..., description="成功的Worker ID")
    failed: Dict[int, str] = Field(..., description="失败的Worker ID及原因")
    total: int = Field(..., description="总数")


class ApiResponse(BaseModel):
    """通用API响应"""
    code: int = Field(default=0, description="状态码: 0成功, 非0失败")
    message: str = Field(default="success", description="响应消息")
    data: Optional[Any] = Field(None, description="响应数据")


class WorkerCloneRequest(BaseModel):
    """克隆Worker请求"""
    new_name: str = Field(..., description="新Worker名称")
    copy_config: bool = Field(default=True, description="是否复制配置")
    copy_parameters: bool = Field(default=True, description="是否复制参数")


class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    worker_id: int = Field(..., description="Worker ID")
    status: str = Field(..., description="状态")
    is_healthy: bool = Field(..., description="是否健康")
    last_heartbeat: Optional[datetime] = Field(None, description="最后心跳")
    uptime: Optional[float] = Field(None, description="运行时间")
    checks: Dict[str, bool] = Field(..., description="各项检查状态")


class TradingSummary(BaseModel):
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_profit: float = 0.0
    total_loss: float = 0.0
    profit_factor: float = 0.0
    average_profit: float = 0.0
    average_loss: float = 0.0
    largest_profit: float = 0.0
    largest_loss: float = 0.0
    total_volume: float = 0.0
    total_fees: float = 0.0
    trading_days: int = 0
    daily_average_trades: float = 0.0


class PositionSummary(BaseModel):
    total_positions: int = 0
    long_positions: int = 0
    short_positions: int = 0
    total_value: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_margin_used: float = 0.0
    positions: List[Dict[str, Any]] = []


class PnLDistribution(BaseModel):
    bins: List[float] = []
    counts: List[int] = []
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0


class TradeHistoryChart(BaseModel):
    dates: List[str] = []
    cumulative_pnl: List[float] = []
    daily_pnl: List[float] = []
    trade_count: List[int] = []
