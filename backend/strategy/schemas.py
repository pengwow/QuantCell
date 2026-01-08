# 策略相关数据模型
# 定义策略API的请求和响应结构

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# 继承自common/schemas.py中的ApiResponse
from common.schemas import ApiResponse


class StrategyParamInfo(BaseModel):
    """
    策略参数信息模型
    """
    name: str = Field(..., description="参数名称", example="n1")
    type: str = Field(..., description="参数类型", example="int")
    default: Any = Field(..., description="默认值", example=10)
    description: str = Field(..., description="参数描述", example="短期移动平均线周期")
    min: Optional[float] = Field(None, description="最小值", example=1)
    max: Optional[float] = Field(None, description="最大值", example=100)
    required: bool = Field(False, description="是否必填", example=False)


class StrategyInfo(BaseModel):
    """
    策略信息模型
    """
    name: str = Field(..., description="策略名称", example="sma_cross")
    file_name: str = Field(..., description="策略文件名", example="sma_cross.py")
    file_path: str = Field(..., description="策略文件路径", example="/backend/strategies/sma_cross.py")
    description: str = Field(..., description="策略描述", example="基于SMA交叉的策略，当短期均线上穿长期均线时买入，下穿时卖出")
    version: str = Field(..., description="策略版本", example="1.0.0")
    params: List[StrategyParamInfo] = Field(default_factory=list, description="策略参数列表", example=[{"name": "n1", "type": "int", "default": 10, "description": "短期移动平均线周期"}])
    created_at: datetime = Field(..., description="创建时间", example="2023-01-01T00:00:00")
    updated_at: datetime = Field(..., description="更新时间", example="2023-01-01T00:00:00")
    code: Optional[str] = Field(None, description="策略代码", example="class SmaCross(Strategy):\n    def next(self):\n        self.buy()")


class StrategyListResponse(ApiResponse):
    """
    策略列表响应模型
    """
    data: Optional[Dict[str, List[StrategyInfo]]] = Field(
        None, 
        description="响应数据，包含策略列表",
        example={"strategies": [{"name": "sma_cross", "file_name": "sma_cross.py", "file_path": "/backend/strategies/sma_cross.py", "description": "基于SMA交叉的策略", "version": "1.0.0", "params": [], "created_at": "2023-01-01T00:00:00", "updated_at": "2023-01-01T00:00:00"}]}
    )


class StrategyUploadRequest(BaseModel):
    """
    策略文件上传请求模型
    """
    strategy_name: str = Field(..., description="策略名称", example="sma_cross")
    file_content: str = Field(..., description="策略文件内容", example="class MyStrategy(Strategy):\n    def next(self):\n        self.buy()")


class StrategyUploadResponse(ApiResponse):
    """
    策略文件上传响应模型
    """
    data: Optional[Dict[str, str]] = Field(
        None, 
        description="响应数据，包含策略名称",
        example={"strategy_name": "sma_cross"}
    )


class StrategyDetailResponse(ApiResponse):
    """
    策略详情响应模型
    """
    data: Optional[Dict[str, StrategyInfo]] = Field(
        None, 
        description="响应数据，包含策略详情",
        example={"strategy": {"name": "sma_cross", "file_name": "sma_cross.py", "file_path": "/backend/strategies/sma_cross.py", "description": "基于SMA交叉的策略", "version": "1.0.0", "params": [], "created_at": "2023-01-01T00:00:00", "updated_at": "2023-01-01T00:00:00", "code": "class SmaCross(Strategy):\n    def next(self):\n        self.buy()"}}
    )


class BacktestConfig(BaseModel):
    """
    回测配置模型
    """
    start_date: str = Field(..., description="回测开始日期", example="2023-01-01")
    end_date: str = Field(..., description="回测结束日期", example="2023-12-31")
    initial_capital: float = Field(..., description="初始资金", example=100000.0)
    commission: Optional[float] = Field(0.0, description="佣金费率", example=0.001)
    slippage: Optional[float] = Field(0.0, description="滑点", example=0.001)


class StrategyExecutionRequest(BaseModel):
    """
    策略执行请求模型
    """
    params: Dict[str, Any] = Field(..., description="策略参数", example={"n1": 10, "n2": 20})
    mode: str = Field(..., description="执行模式", example="backtest", pattern="^(backtest|live)$")
    backtest_config: Optional[BacktestConfig] = Field(None, description="回测配置")


class StrategyExecutionResponse(ApiResponse):
    """
    策略执行响应模型
    """
    data: Optional[Dict[str, Any]] = Field(
        None, 
        description="响应数据，包含执行ID和状态",
        example={"execution_id": "uuid-1234-5678", "status": "running", "result_url": "/api/strategy/execution/uuid-1234-5678/result"}
    )
