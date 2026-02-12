"""
策略模块数据模型

定义策略API的请求和响应数据结构。

包含模型:
    - 策略信息模型
    - 策略参数模型
    - 策略上传/下载模型
    - 策略执行模型

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from common.schemas import ApiResponse


class BaseSchema(BaseModel):
    """基础模型类"""

    class Config:
        json_encoders = {}
        orm_mode = True


class StrategyParamInfo(BaseSchema):
    """
    策略参数信息模型

    Attributes:
        name: 参数名称
        type: 参数类型
        default: 默认值
        description: 参数描述
        min: 最小值
        max: 最大值
        required: 是否必填
    """

    name: str = Field(..., min_length=1, description="参数名称")
    type: str = Field(..., description="参数类型")
    default: Any = Field(..., description="默认值")
    description: str = Field(default="", description="参数描述")
    min: Optional[float] = Field(default=None, description="最小值")
    max: Optional[float] = Field(default=None, description="最大值")
    required: bool = Field(default=False, description="是否必填")


class StrategyInfo(BaseSchema):
    """
    策略信息模型

    Attributes:
        name: 策略名称
        file_name: 策略文件名
        file_path: 策略文件路径
        description: 策略描述
        version: 策略版本
        params: 策略参数列表
        created_at: 创建时间
        updated_at: 更新时间
        code: 策略代码
        source: 策略来源
    """

    name: str = Field(..., min_length=1, description="策略名称")
    file_name: str = Field(..., description="策略文件名")
    file_path: str = Field(..., description="策略文件路径")
    description: str = Field(default="", description="策略描述")
    version: str = Field(default="1.0.0", description="策略版本")
    tags: List[str] = Field(default_factory=list, description="策略标签")
    params: List[StrategyParamInfo] = Field(default_factory=list, description="策略参数列表")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    code: Optional[str] = Field(default=None, description="策略代码")
    source: str = Field(default="files", description="策略来源")


class StrategyListResponse(ApiResponse):
    """
    策略列表响应模型

    Attributes:
        data: 响应数据，包含策略列表
    """

    data: Optional[Dict[str, List[StrategyInfo]]] = Field(
        default=None,
        description="响应数据，包含策略列表",
    )


class StrategyUploadRequest(BaseSchema):
    """
    策略文件上传请求模型

    Attributes:
        id: 策略ID（可选）
        strategy_name: 策略名称
        file_content: 策略文件内容
        version: 策略版本（可选）
        tags: 策略标签（可选）
        description: 策略描述（可选）
    """

    id: Optional[int] = Field(default=None, description="策略ID（可选）")
    strategy_name: str = Field(..., min_length=1, max_length=100, description="策略名称")
    file_content: str = Field(..., min_length=1, description="策略文件内容")
    version: Optional[str] = Field(default=None, description="策略版本（可选）")
    tags: Optional[List[str]] = Field(default=None, description="策略标签（可选）")
    description: Optional[str] = Field(default=None, description="策略描述（可选）")


class StrategyDetailRequest(BaseSchema):
    """
    策略详情请求模型

    Attributes:
        strategy_name: 策略名称
        file_content: 策略文件内容（可选）
    """

    strategy_name: str = Field(..., min_length=1, description="策略名称")
    file_content: Optional[str] = Field(default=None, description="策略文件内容（可选）")


class StrategyUploadResponse(ApiResponse):
    """
    策略文件上传响应模型

    Attributes:
        data: 响应数据，包含策略名称
    """

    data: Optional[Dict[str, str]] = Field(
        default=None,
        description="响应数据，包含策略名称",
    )


class StrategyDetailResponse(BaseSchema):
    """
    策略详情响应模型

    Attributes:
        code: 响应状态码
        message: 响应消息
        data: 策略详情
        timestamp: 响应时间戳
    """

    code: int = Field(..., description="响应状态码")
    message: str = Field(..., description="响应消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="策略详情")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间戳")


class BacktestConfig(BaseSchema):
    """
    回测配置模型

    Attributes:
        start_date: 回测开始日期
        end_date: 回测结束日期
        initial_capital: 初始资金
        commission: 佣金费率
        slippage: 滑点
    """

    start_date: str = Field(..., description="回测开始日期")
    end_date: str = Field(..., description="回测结束日期")
    initial_capital: float = Field(..., gt=0, description="初始资金")
    commission: Optional[float] = Field(default=0.0, ge=0, description="佣金费率")
    slippage: Optional[float] = Field(default=0.0, ge=0, description="滑点")


class StrategyExecutionRequest(BaseSchema):
    """
    策略执行请求模型

    Attributes:
        params: 策略参数
        mode: 执行模式
        backtest_config: 回测配置
    """

    params: Dict[str, Any] = Field(..., description="策略参数")
    mode: str = Field(..., description="执行模式")
    backtest_config: Optional[BacktestConfig] = Field(default=None, description="回测配置")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """验证执行模式"""
        if v not in ["backtest", "live"]:
            raise ValueError("执行模式必须是 backtest 或 live")
        return v


class StrategyExecutionResponse(ApiResponse):
    """
    策略执行响应模型

    Attributes:
        data: 响应数据，包含执行ID和状态
    """

    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="响应数据，包含执行ID和状态",
    )


class StrategyParseRequest(BaseSchema):
    """
    策略脚本解析请求模型

    Attributes:
        strategy_name: 策略名称
        file_content: 策略文件内容
    """

    strategy_name: str = Field(..., min_length=1, description="策略名称")
    file_content: str = Field(..., min_length=1, description="策略文件内容")


class StrategyParseResponse(ApiResponse):
    """
    策略脚本解析响应模型

    Attributes:
        data: 响应数据，包含策略描述和参数信息
    """

    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="响应数据，包含策略描述和参数信息",
    )
