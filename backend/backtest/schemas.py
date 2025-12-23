# 回测服务API数据模型

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """
    API响应通用模型
    """
    code: int = Field(..., description="响应码，0表示成功，非0表示失败")
    message: str = Field(..., description="响应消息")
    data: Dict[str, Any] = Field(default_factory=dict, description="响应数据")


class BacktestListRequest(BaseModel):
    """
    获取回测列表请求模型
    """
    pass


class BacktestRunRequest(BaseModel):
    """
    执行回测请求模型
    """
    strategy_config: Dict[str, Any] = Field(..., description="策略配置")
    executor_config: Dict[str, Any] = Field(..., description="执行器配置")
    backtest_config: Dict[str, Any] = Field(..., description="回测配置")


class BacktestAnalyzeRequest(BaseModel):
    """
    分析回测结果请求模型
    """
    backtest_name: str = Field(..., description="回测名称")


class BacktestDeleteRequest(BaseModel):
    """
    删除回测结果请求模型
    """
    backtest_name: str = Field(..., description="回测名称")


class StrategyConfigRequest(BaseModel):
    """
    创建策略配置请求模型
    """
    strategy_type: str = Field(..., description="策略类型")
    params: Dict[str, Any] = Field(..., description="策略参数")


class ExecutorConfigRequest(BaseModel):
    """
    创建执行器配置请求模型
    """
    executor_type: str = Field(..., description="执行器类型")
    params: Dict[str, Any] = Field(..., description="执行器参数")


class BacktestListResponse(BaseModel):
    """
    回测列表响应模型
    """
    backtests: List[str] = Field(..., description="回测结果列表")


class BacktestRunResponse(BaseModel):
    """
    回测执行响应模型
    """
    backtest_name: str = Field(..., description="回测名称")
    status: str = Field(..., description="回测状态")
    message: str = Field(..., description="回测消息")
    portfolio_metrics: Optional[Dict[str, Any]] = Field(None, description="组合指标")
    indicator: Optional[Dict[str, Any]] = Field(None, description="回测指标")


class BacktestAnalyzeResponse(BaseModel):
    """
    回测分析响应模型
    """
    backtest_name: str = Field(..., description="回测名称")
    status: str = Field(..., description="分析状态")
    message: str = Field(..., description="分析消息")
    portfolio_metrics: Optional[Dict[str, Any]] = Field(None, description="组合指标")
    indicator: Optional[Dict[str, Any]] = Field(None, description="回测指标")
    ic: Optional[float] = Field(None, description="信息系数")
    ir: Optional[float] = Field(None, description="信息比率")
    group_results: Optional[Dict[str, Any]] = Field(None, description="分组回测结果")


class StrategyConfig(BaseModel):
    """
    策略配置模型
    """
    strategy_type: str = Field(..., description="策略类型")
    params: Dict[str, Any] = Field(..., description="策略参数")


class ExecutorConfig(BaseModel):
    """
    执行器配置模型
    """
    executor_type: str = Field(..., description="执行器类型")
    params: Dict[str, Any] = Field(..., description="执行器参数")


class BacktestConfig(BaseModel):
    """
    回测配置模型
    """
    name: str = Field(default="default_backtest", description="回测名称")
    start_time: str = Field(..., description="开始时间")
    end_time: str = Field(..., description="结束时间")
    benchmark: Optional[str] = Field(None, description="基准")
    account: int = Field(default=100000000, description="账户资金")
    frequency: str = Field(default="day", description="频率")
    verbose: bool = Field(default=True, description="是否打印详细信息")
