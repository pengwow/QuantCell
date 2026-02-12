"""
回测模块数据模型

定义回测API的请求和响应数据结构。

包含模型:
    - 回测配置模型
    - 策略配置模型
    - 回测结果模型
    - 数据完整性检查模型

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from common.schemas import ApiResponse, PaginationRequest


class BaseSchema(BaseModel):
    """基础模型类"""

    class Config:
        json_encoders = {}
        orm_mode = True


class BacktestConfig(BaseSchema):
    """
    回测配置模型

    Attributes:
        symbols: 回测交易对列表
        interval: K线周期
        start_time: 开始时间
        end_time: 结束时间
        initial_cash: 初始资金
        commission: 手续费率
        exclusive_orders: 是否取消未完成订单
    """

    symbols: List[str] = Field(
        ...,
        min_length=1,
        description="回测交易对列表",
        json_schema_extra={"example": ["BTCUSDT", "ETHUSDT"]},
    )
    interval: str = Field(
        default="1d",
        description="K线周期",
        json_schema_extra={"example": "1d"},
    )
    start_time: str = Field(
        ...,
        description="开始时间",
        json_schema_extra={"example": "2023-01-01 00:00:00"},
    )
    end_time: str = Field(
        ...,
        description="结束时间",
        json_schema_extra={"example": "2023-12-31 23:59:59"},
    )
    initial_cash: float = Field(
        default=10000.0,
        ge=0,
        description="初始资金",
        json_schema_extra={"example": 10000.0},
    )
    commission: float = Field(
        default=0.001,
        ge=0,
        le=1,
        description="手续费率",
        json_schema_extra={"example": 0.001},
    )
    exclusive_orders: bool = Field(
        default=True,
        description="是否取消未完成订单",
        json_schema_extra={"example": True},
    )


class StrategyConfig(BaseSchema):
    """
    策略配置模型

    Attributes:
        strategy_name: 策略名称
        params: 策略参数
    """

    strategy_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="策略名称",
        json_schema_extra={"example": "SmaCross"},
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数",
        json_schema_extra={"example": {"n1": 10, "n2": 20}},
    )


class BacktestRunRequest(BaseSchema):
    """
    执行回测请求模型

    Attributes:
        strategy_config: 策略配置
        backtest_config: 回测配置
    """

    strategy_config: StrategyConfig = Field(
        ...,
        description="策略配置",
    )
    backtest_config: BacktestConfig = Field(
        ...,
        description="回测配置",
    )


class TradeItem(BaseSchema):
    """
    交易记录项模型

    Attributes:
        EntryTime: 开仓时间
        ExitTime: 平仓时间
        EntryPrice: 开仓价格
        ExitPrice: 平仓价格
        Size: 交易数量
        PnL: 盈亏
        ReturnPct: 收益率(%)
        Direction: 方向(多/空)
    """

    EntryTime: str = Field(..., description="开仓时间")
    ExitTime: str = Field(..., description="平仓时间")
    EntryPrice: float = Field(..., ge=0, description="开仓价格")
    ExitPrice: float = Field(..., ge=0, description="平仓价格")
    Size: float = Field(..., description="交易数量")
    PnL: float = Field(..., description="盈亏")
    ReturnPct: float = Field(..., description="收益率(%)")
    Direction: str = Field(..., description="方向(多/空)")


class EquityPoint(BaseSchema):
    """
    资金曲线点模型

    Attributes:
        timestamp: 时间戳
        equity: 资金权益
        drawdown: 回撤
        drawdown_pct: 回撤百分比
    """

    timestamp: Any = Field(..., description="时间戳")
    equity: float = Field(..., ge=0, description="资金权益")
    drawdown: float = Field(..., description="回撤")
    drawdown_pct: float = Field(..., description="回撤百分比")


class BacktestResult(BaseSchema):
    """
    回测结果详情模型

    Attributes:
        task_id: 任务ID
        strategy_name: 策略名称
        backtest_config: 回测配置
        metrics: 回测指标
        trades: 交易记录列表
        equity_curve: 资金曲线数据
        strategy_data: 策略指标数据
    """

    task_id: str = Field(..., description="任务ID")
    strategy_name: str = Field(..., description="策略名称")
    backtest_config: BacktestConfig = Field(..., description="回测配置")
    metrics: Dict[str, Any] = Field(..., description="回测指标")
    trades: List[Dict[str, Any]] = Field(..., description="交易记录列表")
    equity_curve: List[Dict[str, Any]] = Field(..., description="资金曲线数据")
    strategy_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="策略指标数据",
    )


class MultiBacktestResult(BaseSchema):
    """
    多货币对回测结果汇总

    Attributes:
        task_ids: 所有子任务ID
        total_metrics: 汇总指标
        results: 各货币对回测结果
    """

    task_ids: List[str] = Field(..., description="所有子任务ID")
    total_metrics: Dict[str, Any] = Field(..., description="汇总指标")
    results: List[BacktestResult] = Field(..., description="各货币对回测结果")


class BacktestRunResponse(ApiResponse):
    """
    执行回测响应模型

    Attributes:
        data: 响应数据，包含任务ID
    """

    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="响应数据，包含任务ID",
    )


class BacktestAnalyzeRequest(BaseSchema):
    """
    回测结果分析请求模型

    Attributes:
        backtest_id: 回测任务ID
    """

    backtest_id: str = Field(
        ...,
        min_length=1,
        description="回测任务ID",
    )


class BacktestAnalyzeResponse(ApiResponse):
    """
    回测结果分析响应模型

    Attributes:
        data: 回测详细结果
    """

    data: Optional[BacktestResult] = Field(default=None, description="回测详细结果")


class BacktestListResponse(ApiResponse):
    """
    回测历史列表响应

    Attributes:
        data: 回测列表数据
    """

    data: Optional[Dict[str, Any]] = Field(default=None, description="回测列表数据")


class ReplayData(BaseSchema):
    """
    回放数据模型

    Attributes:
        kline: K线数据
        trades: 交易信号
        equity: 资金曲线
        indicators: 技术指标数据
    """

    kline: List[Dict[str, Any]] = Field(..., description="K线数据")
    trades: List[Dict[str, Any]] = Field(..., description="交易信号")
    equity: List[Dict[str, Any]] = Field(..., description="资金曲线")
    indicators: Dict[str, List[Dict[str, Any]]] = Field(..., description="技术指标数据")


class BacktestReplayResponse(ApiResponse):
    """
    回测回放数据响应

    Attributes:
        data: 回放数据
    """

    data: Optional[ReplayData] = Field(default=None, description="回放数据")


class BacktestListRequest(PaginationRequest):
    """
    回测列表请求模型

    继承自PaginationRequest，支持分页查询
    """
    pass


class BacktestDeleteRequest(BaseSchema):
    """
    删除回测请求模型

    Attributes:
        backtest_id: 回测ID
    """

    backtest_id: str = Field(
        ...,
        min_length=1,
        description="回测ID",
    )


class BacktestStopRequest(BaseSchema):
    """
    终止回测请求模型

    Attributes:
        task_id: 回测任务ID
    """

    task_id: str = Field(
        ...,
        min_length=1,
        description="回测任务ID",
    )


class StrategyConfigRequest(BaseSchema):
    """
    策略配置请求模型

    Attributes:
        strategy_name: 策略名称
        params: 策略参数
    """

    strategy_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="策略名称",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数",
    )


class BacktestReplayRequest(BaseSchema):
    """
    回测回放请求模型

    Attributes:
        backtest_id: 回测ID
        symbol: 货币对，用于多货币对回测结果筛选
    """

    backtest_id: str = Field(
        ...,
        min_length=1,
        description="回测ID",
    )
    symbol: Optional[str] = Field(
        default=None,
        description="货币对，用于多货币对回测结果筛选",
    )


class DataIntegrityCheckRequest(BaseSchema):
    """
    数据完整性检查请求模型

    Attributes:
        symbol: 交易对符号
        interval: 时间周期
        start_time: 开始时间
        end_time: 结束时间
        market_type: 市场类型
        crypto_type: 加密货币类型
    """

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="交易对符号",
    )
    interval: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="时间周期",
    )
    start_time: str = Field(
        ...,
        description="开始时间",
    )
    end_time: str = Field(
        ...,
        description="结束时间",
    )
    market_type: str = Field(
        default="crypto",
        description="市场类型",
    )
    crypto_type: str = Field(
        default="spot",
        description="加密货币类型",
    )


class MissingRange(BaseSchema):
    """
    缺失时间段模型

    Attributes:
        start: 开始时间
        end: 结束时间
    """

    start: str = Field(..., description="开始时间")
    end: str = Field(..., description="结束时间")


class QualityIssue(BaseSchema):
    """
    数据质量问题模型

    Attributes:
        type: 问题类型
        column: 相关列名
        count: 问题数量
        message: 问题描述
    """

    type: str = Field(..., description="问题类型")
    column: Optional[str] = Field(default=None, description="相关列名")
    count: Optional[int] = Field(default=None, ge=0, description="问题数量")
    message: str = Field(..., description="问题描述")


class DataIntegrityResult(BaseSchema):
    """
    数据完整性检查结果模型

    Attributes:
        is_complete: 是否完整
        total_expected: 期望数据条数
        total_actual: 实际数据条数
        missing_count: 缺失条数
        missing_ranges: 缺失时间段列表
        quality_issues: 数据质量问题列表
        coverage_percent: 覆盖率百分比
    """

    is_complete: bool = Field(..., description="是否完整")
    total_expected: int = Field(..., ge=0, description="期望数据条数")
    total_actual: int = Field(..., ge=0, description="实际数据条数")
    missing_count: int = Field(..., ge=0, description="缺失条数")
    missing_ranges: List[MissingRange] = Field(
        default_factory=list,
        description="缺失时间段列表",
    )
    quality_issues: List[QualityIssue] = Field(
        default_factory=list,
        description="数据质量问题列表",
    )
    coverage_percent: float = Field(..., ge=0, le=100, description="覆盖率百分比")


class DataIntegrityCheckResponse(ApiResponse):
    """
    数据完整性检查响应模型

    Attributes:
        data: 检查结果
    """

    data: Optional[DataIntegrityResult] = Field(default=None, description="检查结果")


class DataDownloadProgress(BaseSchema):
    """
    数据下载进度模型

    Attributes:
        task_id: 任务ID
        symbol: 交易对符号
        interval: 时间周期
        status: 状态
        progress: 进度百分比
        message: 状态消息
        created_at: 创建时间
        updated_at: 更新时间
        error: 错误信息
    """

    task_id: str = Field(..., description="任务ID")
    symbol: str = Field(..., description="交易对符号")
    interval: str = Field(..., description="时间周期")
    status: str = Field(..., description="状态: pending, downloading, completed, failed")
    progress: float = Field(..., ge=0, le=100, description="进度百分比")
    message: str = Field(..., description="状态消息")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    error: Optional[str] = Field(default=None, description="错误信息")


class DataDownloadResponse(ApiResponse):
    """
    数据下载响应模型

    Attributes:
        data: 下载进度信息
    """

    data: Optional[DataDownloadProgress] = Field(default=None, description="下载进度信息")
