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

    name: str = Field(..., description="参数名称", json_schema_extra={"example": "n1"})
    type: str = Field(..., description="参数类型", json_schema_extra={"example": "int"})
    default: Any = Field(..., description="默认值", json_schema_extra={"example": 10})
    description: str = Field(..., description="参数描述", json_schema_extra={"example": "短期移动平均线周期"})
    min: Optional[float] = Field(None, description="最小值", json_schema_extra={"example": 1})
    max: Optional[float] = Field(None, description="最大值", json_schema_extra={"example": 100})
    required: bool = Field(False, description="是否必填", json_schema_extra={"example": False})


class StrategyInfo(BaseModel):
    """
    策略信息模型
    """

    name: str = Field(..., description="策略名称", json_schema_extra={"example": "sma_cross"})
    file_name: str = Field(..., description="策略文件名", json_schema_extra={"example": "sma_cross.py"})
    file_path: str = Field(
        ..., description="策略文件路径", json_schema_extra={"example": "/backend/strategies/sma_cross.py"}
    )
    description: str = Field(
        ...,
        description="策略描述",
        json_schema_extra={"example": "基于SMA交叉的策略，当短期均线上穿长期均线时买入，下穿时卖出"},
    )
    version: str = Field(..., description="策略版本", json_schema_extra={"example": "1.0.0"})
    params: List[StrategyParamInfo] = Field(
        default_factory=list,
        description="策略参数列表",
        json_schema_extra={"example": [
            {
                "name": "n1",
                "type": "int",
                "default": 10,
                "description": "短期移动平均线周期",
            }
        ]},
    )
    created_at: datetime = Field(
        ..., description="创建时间", json_schema_extra={"example": "2023-01-01T00:00:00"}
    )
    updated_at: datetime = Field(
        ..., description="更新时间", json_schema_extra={"example": "2023-01-01T00:00:00"}
    )
    code: Optional[str] = Field(
        None,
        description="策略代码",
        json_schema_extra={"example": "class SmaCross(Strategy):\n    def next(self):\n        self.buy()"},
    )
    source: str = Field(..., description="策略来源", json_schema_extra={"example": "files"})


class StrategyListResponse(ApiResponse):
    """
    策略列表响应模型
    """

    data: Optional[Dict[str, List[StrategyInfo]]] = Field(
        None,
        description="响应数据，包含策略列表",
        json_schema_extra={"example": {
            "strategies": [
                {
                    "name": "sma_cross",
                    "file_name": "sma_cross.py",
                    "file_path": "/backend/strategies/sma_cross.py",
                    "description": "基于SMA交叉的策略",
                    "version": "1.0.0",
                    "params": [],
                    "created_at": "2023-01-01T00:00:00",
                    "updated_at": "2023-01-01T00:00:00",
                }
            ]
        }},
    )


class StrategyUploadRequest(BaseModel):
    """
    策略文件上传请求模型
    """

    id: Optional[int] = Field(
        None,
        description="策略ID（可选），如果提供则更新现有策略，否则创建新策略",
        json_schema_extra={"example": 1},
    )
    strategy_name: str = Field(..., description="策略名称", json_schema_extra={"example": "sma_cross"})
    file_content: str = Field(
        ...,
        description="策略文件内容",
        json_schema_extra={"example": "class MyStrategy(Strategy):\n    def next(self):\n        self.buy()"},
    )
    version: Optional[str] = Field(
        None,
        description="策略版本（可选），如果提供则使用，否则从文件内容中提取",
        json_schema_extra={"example": "1.0.0"},
    )
    tags: Optional[List[str]] = Field(
        None,
        description="策略标签（可选）",
        json_schema_extra={"example": ["demo", "trend"]},
    )
    description: Optional[str] = Field(
        None,
        description="策略描述（可选），如果提供则使用，否则从文件内容中提取",
        json_schema_extra={"example": "基于SMA交叉的策略"},
    )


class StrategyDetailRequest(BaseModel):
    """
    策略详情请求模型
    """

    strategy_name: str = Field(..., description="策略名称", json_schema_extra={"example": "sma_cross"})
    file_content: Optional[str] = Field(
        None,
        description="策略文件内容（可选），如果提供则直接解析",
        json_schema_extra={"example": "class MyStrategy(Strategy):\n    def next(self):\n        self.buy()"},
    )


class StrategyUploadResponse(ApiResponse):
    """
    策略文件上传响应模型
    """

    data: Optional[Dict[str, str]] = Field(
        None,
        description="响应数据，包含策略名称",
        json_schema_extra={"example": {"strategy_name": "sma_cross"}},
    )



from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class StrategyDetailResponse(BaseModel):
    """
    策略详情响应模型
    """
    code: int = Field(..., description="响应状态码", json_schema_extra={"example": 0})
    message: str = Field(..., description="响应消息", json_schema_extra={"example": "获取策略详情成功"})
    data: Optional[Dict[str, Any]] = Field(None, description="策略详情")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间戳")


class BacktestConfig(BaseModel):
    """
    回测配置模型
    """

    start_date: str = Field(..., description="回测开始日期", json_schema_extra={"example": "2023-01-01"})
    end_date: str = Field(..., description="回测结束日期", json_schema_extra={"example": "2023-12-31"})
    initial_capital: float = Field(..., description="初始资金", json_schema_extra={"example": 100000.0})
    commission: Optional[float] = Field(0.0, description="佣金费率", json_schema_extra={"example": 0.001})
    slippage: Optional[float] = Field(0.0, description="滑点", json_schema_extra={"example": 0.001})


class StrategyExecutionRequest(BaseModel):
    """
    策略执行请求模型
    """

    params: Dict[str, Any] = Field(
        ..., description="策略参数", json_schema_extra={"example": {"n1": 10, "n2": 20}}
    )
    mode: str = Field(
        ..., description="执行模式", json_schema_extra={"example": "backtest"}, pattern="^(backtest|live)$"
    )
    backtest_config: Optional[BacktestConfig] = Field(None, description="回测配置")


class StrategyExecutionResponse(ApiResponse):
    """
    策略执行响应模型
    """

    data: Optional[Dict[str, Any]] = Field(
        None,
        description="响应数据，包含执行ID和状态",
        json_schema_extra={"example": {
            "execution_id": "uuid-1234-5678",
            "status": "running",
            "result_url": "/api/strategy/execution/uuid-1234-5678/result",
        }},
    )


class StrategyParseRequest(BaseModel):
    """
    策略脚本解析请求模型
    """

    strategy_name: str = Field(..., description="策略名称", json_schema_extra={"example": "sma_cross"})
    file_content: str = Field(
        ...,
        description="策略文件内容",
        json_schema_extra={"example": "class MyStrategy(Strategy):\n    def next(self):\n        self.buy()"},
    )


class StrategyParseResponse(ApiResponse):
    """
    策略脚本解析响应模型
    """

    data: Optional[Dict[str, Any]] = Field(
        None,
        description="响应数据，包含策略描述和参数信息",
        json_schema_extra={"example": {
            "strategy": {
                "name": "sma_cross",
                "description": "基于SMA交叉的策略，当短期均线上穿长期均线时买入，下穿时卖出",
                "params": [
                    {
                        "name": "n1",
                        "type": "int",
                        "default": 10,
                        "description": "短期移动平均线周期",
                    },
                    {
                        "name": "n2",
                        "type": "int",
                        "default": 20,
                        "description": "长期移动平均线周期",
                    },
                ],
            }
        }},
    )
