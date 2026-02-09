# 回测相关数据模型
# 定义回测API的请求和响应结构

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# 继承自common/schemas.py中的ApiResponse
from common.schemas import ApiResponse, PaginationRequest


class BacktestConfig(BaseModel):
    """
    回测配置模型
    """

    symbols: List[str] = Field(
        ...,
        description="回测交易对列表",
        json_schema_extra={"example": ["BTCUSDT", "ETHUSDT"]},
        min_length=1,
    )
    interval: str = Field(
        "1d",
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
        10000.0,
        description="初始资金",
        json_schema_extra={"example": 10000.0},
    )
    commission: float = Field(
        0.001,
        description="手续费率",
        json_schema_extra={"example": 0.001},
    )
    exclusive_orders: bool = Field(
        True,
        description="是否取消未完成订单",
        json_schema_extra={"example": True},
    )


class StrategyConfig(BaseModel):
    """
    策略配置模型
    """

    strategy_name: str = Field(
        ...,
        description="策略名称",
        json_schema_extra={"example": "SmaCross"},
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数",
        json_schema_extra={"example": {"n1": 10, "n2": 20}},
    )


class BacktestRunRequest(BaseModel):
    """
    执行回测请求模型
    """

    strategy_config: StrategyConfig = Field(
        ...,
        description="策略配置",
        json_schema_extra={"example": {
            "strategy_name": "SmaCross",
            "params": {"n1": 10, "n2": 20}
        }},
    )
    backtest_config: BacktestConfig = Field(
        ...,
        description="回测配置",
        json_schema_extra={"example": {
            "symbols": ["BTCUSDT"],
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59",
            "initial_cash": 10000.0,
            "commission": 0.001
        }},
    )


class TradeItem(BaseModel):
    """
    交易记录项模型
    """

    EntryTime: str = Field(..., description="开仓时间", json_schema_extra={"example": "2023-01-02 10:00:00"})
    ExitTime: str = Field(..., description="平仓时间", json_schema_extra={"example": "2023-01-05 14:00:00"})
    EntryPrice: float = Field(..., description="开仓价格", json_schema_extra={"example": 20000.0})
    ExitPrice: float = Field(..., description="平仓价格", json_schema_extra={"example": 21000.0})
    Size: float = Field(..., description="交易数量", json_schema_extra={"example": 0.1})
    PnL: float = Field(..., description="盈亏", json_schema_extra={"example": 100.0})
    ReturnPct: float = Field(..., description="收益率(%)", json_schema_extra={"example": 5.0})
    Direction: str = Field(..., description="方向(多/空)", json_schema_extra={"example": "多单"})


class EquityPoint(BaseModel):
    """
    资金曲线点模型
    """

    timestamp: Any = Field(..., description="时间戳")
    equity: float = Field(..., description="资金权益")
    drawdown: float = Field(..., description="回撤")
    drawdown_pct: float = Field(..., description="回撤百分比")


class BacktestResult(BaseModel):
    """
    回测结果详情模型
    """

    task_id: str = Field(..., description="任务ID", json_schema_extra={"example": "SmaCross_BTCUSDT_20230101"})
    strategy_name: str = Field(..., description="策略名称", json_schema_extra={"example": "SmaCross"})
    backtest_config: BacktestConfig = Field(..., description="回测配置")
    metrics: Dict[str, Any] = Field(
        ...,
        description="回测指标",
        json_schema_extra={"example": {
            "Return [%]": 15.5,
            "Sharpe Ratio": 1.2,
            "Max Drawdown [%]": -5.4,
            "Win Rate [%]": 60.0
        }},
    )
    trades: List[Dict[str, Any]] = Field(
        ...,
        description="交易记录列表",
        json_schema_extra={"example": [{
            "EntryTime": "2023-01-01",
            "ExitTime": "2023-01-05",
            "EntryPrice": 20000,
            "ExitPrice": 21000,
            "PnL": 100
        }]},
    )
    equity_curve: List[Dict[str, Any]] = Field(
        ...,
        description="资金曲线数据",
        json_schema_extra={"example": [{
            "timestamp": 1672531200000,
            "Equity": 10000,
            "DrawdownPct": 0
        }]},
    )
    strategy_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="策略指标数据(SMA等)",
        json_schema_extra={"example": [{
            "datetime": 1672531200000,
            "SMA1": 20000,
            "SMA2": 19500
        }]},
    )


class MultiBacktestResult(BaseModel):
    """
    多货币对回测结果汇总
    """
    
    task_ids: List[str] = Field(..., description="所有子任务ID")
    total_metrics: Dict[str, Any] = Field(..., description="汇总指标")
    results: List[BacktestResult] = Field(..., description="各货币对回测结果")


class BacktestRunResponse(ApiResponse):
    """
    执行回测响应模型
    """

    data: Optional[Dict[str, Any]] = Field(
        None,
        description="响应数据，包含任务ID",
        json_schema_extra={"example": {"task_id": "SmaCross_BTCUSDT_20230101_120000"}},
    )


class BacktestAnalyzeRequest(BaseModel):
    """
    回测结果分析请求模型
    """
    
    backtest_id: str = Field(
        ...,
        description="回测任务ID",
        json_schema_extra={"example": "SmaCross_BTCUSDT_20230101_120000"}
    )


class BacktestAnalyzeResponse(ApiResponse):
    """
    回测结果分析响应模型
    """
    
    data: Optional[BacktestResult] = Field(None, description="回测详细结果")


class BacktestListResponse(ApiResponse):
    """
    回测历史列表响应
    """
    
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="回测列表数据",
        json_schema_extra={"example": {
            "total": 10,
            "items": [
                {
                    "id": "SmaCross_BTCUSDT_20230101",
                    "strategy_name": "SmaCross",
                    "status": "completed",
                    "created_at": "2023-01-01 12:00:00"
                }
            ]
        }}
    )


class ReplayData(BaseModel):
    """
    回放数据模型
    """
    
    kline: List[Dict[str, Any]] = Field(..., description="K线数据")
    trades: List[Dict[str, Any]] = Field(..., description="交易信号")
    equity: List[Dict[str, Any]] = Field(..., description="资金曲线")
    indicators: Dict[str, List[Dict[str, Any]]] = Field(..., description="技术指标数据")


class BacktestReplayResponse(ApiResponse):
    """
    回测回放数据响应
    """
    
    data: Optional[ReplayData] = Field(None, description="回放数据")


class BacktestListRequest(PaginationRequest):
    """
    回测列表请求模型
    """
    pass


class BacktestDeleteRequest(BaseModel):
    """
    删除回测请求模型
    """
    backtest_id: str = Field(..., description="回测ID", json_schema_extra={"example": "SmaCross_BTCUSDT_20230101"})


class BacktestStopRequest(BaseModel):
    """
    终止回测请求模型
    """
    task_id: str = Field(..., description="回测任务ID", json_schema_extra={"example": "bt_1234567890"})


class StrategyConfigRequest(BaseModel):
    """
    策略配置请求模型
    """
    strategy_name: str = Field(..., description="策略名称", json_schema_extra={"example": "SmaCross"})
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数",
        json_schema_extra={"example": {"n1": 10, "n2": 20}},
    )


class BacktestReplayRequest(BaseModel):
    """
    回测回放请求模型
    """
    backtest_id: str = Field(..., description="回测ID", json_schema_extra={"example": "SmaCross_BTCUSDT_20230101"})
    symbol: Optional[str] = Field(None, description="货币对，用于多货币对回测结果筛选", json_schema_extra={"example": "BTCUSDT"})


class DataIntegrityCheckRequest(BaseModel):
    """
    数据完整性检查请求模型
    """
    symbol: str = Field(..., description="交易对符号", json_schema_extra={"example": "BTCUSDT"})
    interval: str = Field(..., description="时间周期", json_schema_extra={"example": "1d"})
    start_time: str = Field(..., description="开始时间", json_schema_extra={"example": "2023-01-01 00:00:00"})
    end_time: str = Field(..., description="结束时间", json_schema_extra={"example": "2023-12-31 23:59:59"})
    market_type: str = Field("crypto", description="市场类型", json_schema_extra={"example": "crypto"})
    crypto_type: str = Field("spot", description="加密货币类型", json_schema_extra={"example": "spot"})


class MissingRange(BaseModel):
    """
    缺失时间段模型
    """
    start: str = Field(..., description="开始时间")
    end: str = Field(..., description="结束时间")


class QualityIssue(BaseModel):
    """
    数据质量问题模型
    """
    type: str = Field(..., description="问题类型")
    column: Optional[str] = Field(None, description="相关列名")
    count: Optional[int] = Field(None, description="问题数量")
    message: str = Field(..., description="问题描述")


class DataIntegrityResult(BaseModel):
    """
    数据完整性检查结果模型
    """
    is_complete: bool = Field(..., description="是否完整")
    total_expected: int = Field(..., description="期望数据条数")
    total_actual: int = Field(..., description="实际数据条数")
    missing_count: int = Field(..., description="缺失条数")
    missing_ranges: List[MissingRange] = Field(default_factory=list, description="缺失时间段列表")
    quality_issues: List[QualityIssue] = Field(default_factory=list, description="数据质量问题列表")
    coverage_percent: float = Field(..., description="覆盖率百分比")


class DataIntegrityCheckResponse(ApiResponse):
    """
    数据完整性检查响应模型
    """
    data: Optional[DataIntegrityResult] = Field(None, description="检查结果")


class DataDownloadProgress(BaseModel):
    """
    数据下载进度模型
    """
    task_id: str = Field(..., description="任务ID")
    symbol: str = Field(..., description="交易对符号")
    interval: str = Field(..., description="时间周期")
    status: str = Field(..., description="状态: pending, downloading, completed, failed")
    progress: float = Field(..., description="进度百分比")
    message: str = Field(..., description="状态消息")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    error: Optional[str] = Field(None, description="错误信息")


class DataDownloadResponse(ApiResponse):
    """
    数据下载响应模型
    """
    data: Optional[DataDownloadProgress] = Field(None, description="下载进度信息")


# Import from strategy schemas to support routes
try:
    from strategy.schemas import StrategyUploadRequest
except ImportError:
    # If circular import or not found, define a placeholder or rely on external import
    # But routes.py imports it from .schemas (this file). 
    # So we should probably define it here or alias it.
    # To avoid circular dependency if strategy imports backtest, we can define it here or move shared schemas.
    # StrategyUploadRequest is simple enough to redefine if needed, but better to import.
    pass

