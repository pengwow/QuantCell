"""
因子计算模块数据模型

定义因子计算相关的Pydantic数据模型。

模型列表：
    - FactorAddRequest: 添加因子请求
    - FactorCalculateRequest: 计算单因子请求
    - FactorCalculateMultiRequest: 计算多因子请求
    - FactorValidateRequest: 验证因子表达式请求
    - FactorCorrelationRequest: 计算因子相关性请求
    - FactorStatsRequest: 获取因子统计请求
    - FactorICRequest: 计算IC请求
    - FactorIRRequest: 计算IR请求
    - FactorGroupAnalysisRequest: 分组分析请求
    - FactorMonotonicityRequest: 单调性检验请求
    - FactorStabilityRequest: 稳定性检验请求
    - FactorData: 因子数据模型
    - FactorResult: 因子计算结果模型
    - FactorInfo: 因子信息模型

验证规则：
    - 时间格式：YYYY-MM-DD
    - 周期 interval：15m/1h/4h/1d 等 K 线周期；candle_type：spot/future
    - 窗口单位为 K 线根数
    - 计算方法：spearman, pearson

作者: QuantCell Team
创建日期: 2024-01-01
"""

from typing import Any

from pydantic import BaseModel, Field, validator


class BaseSchema(BaseModel):
    """基础模型"""

    class Config:
        """Pydantic配置"""

        json_encoders = {}
        from_attributes = True


class FactorAddRequest(BaseSchema):
    """
    添加因子请求模型

    Attributes:
        factor_name: 因子名称
        expression: 因子表达式，用于计算因子值
    """

    factor_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="因子名称",
        example="my_factor",
    )
    expression: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="因子表达式，用于计算因子值",
        example="close - open",
    )

    @validator("factor_name")
    def validate_factor_name(cls, v: str) -> str:
        """验证因子名称"""
        if not v.strip():
            msg = "因子名称不能为空"
            raise ValueError(msg)
        return v.strip()

    @validator("expression")
    def validate_expression(cls, v: str) -> str:
        """验证因子表达式"""
        if not v.strip():
            msg = "因子表达式不能为空"
            raise ValueError(msg)
        return v.strip()


class FactorCalculateBase(BaseSchema):
    """因子计算公共参数：标的 + K线周期 + 时间范围。"""

    instruments: list[str] = Field(
        ...,
        min_items=1,
        description="交易对列表",
        example=["BTCUSDT", "ETHUSDT"],
    )
    interval: str = Field(default="1h", min_length=1, description="K线周期，如 15m/1h/4h/1d")
    candle_type: str = Field(default="spot", description="市场类型：spot/future")
    start_time: str | None = Field(default=None, description="开始日期 YYYY-MM-DD，空=全部")
    end_time: str | None = Field(default=None, description="结束日期 YYYY-MM-DD，空=至今")

    @validator("candle_type")
    def validate_candle_type(cls, v: str) -> str:
        """校验市场类型"""
        if v not in {"spot", "future"}:
            raise ValueError("candle_type 必须为 spot 或 future")
        return v


class FactorCalculateRequest(FactorCalculateBase):
    """单因子计算请求"""

    factor_name: str = Field(..., min_length=1, max_length=100, description="因子名称")


class FactorCalculateMultiRequest(FactorCalculateBase):
    """多因子计算请求"""

    factor_names: list[str] = Field(
        ...,
        min_items=1,
        description="因子名称列表",
        example=["momentum_5d", "rsi_14d"],
    )


class FactorAnalyzeRequest(FactorCalculateBase):
    """一站式因子分析请求（窗口单位为 K 线根数）"""

    factor_name: str = Field(..., min_length=1, max_length=100, description="因子名称")
    method: str = Field(default="spearman", description="相关性方法：spearman/pearson")
    n_groups: int = Field(default=5, ge=2, le=10, description="分组数量")
    window: int = Field(default=20, ge=5, le=252, description="滚动窗口（K线根数）")
    forward: int = Field(default=1, ge=1, le=120, description="前瞻收益的K线根数")

    @validator("method")
    def validate_method(cls, v: str) -> str:
        """校验相关性方法"""
        if v not in {"spearman", "pearson"}:
            raise ValueError("method 必须为 spearman 或 pearson")
        return v


class FactorDetail(BaseSchema):
    """因子明细（因子库展示）"""

    name: str
    expression: str
    category: str
    label: str
    builtin: bool
    supported: bool


class FactorValidateRequest(BaseSchema):
    """
    验证因子表达式请求模型

    Attributes:
        expression: 因子表达式，用于验证其语法正确性
    """

    expression: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="因子表达式，用于验证其语法正确性",
        example="close - open",
    )


class FactorCorrelationRequest(BaseSchema):
    """
    计算因子相关性请求模型

    Attributes:
        factor_data: 因子数据，包含不同因子的计算结果
    """

    factor_data: dict[str, Any] = Field(
        ...,
        description="因子数据，包含不同因子的计算结果",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            },
            "factor2": {
                "BTCUSDT": [0.7, 0.8, 0.9],
                "ETHUSDT": [1.0, 1.1, 1.2],
            },
        },
    )


class FactorStatsRequest(BaseSchema):
    """
    获取因子统计信息请求模型

    Attributes:
        factor_data: 因子数据，用于计算统计信息
    """

    factor_data: dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算统计信息",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )


class FactorICRequest(BaseSchema):
    """
    计算因子IC请求模型

    Attributes:
        factor_data: 因子数据，用于计算IC值
        return_data: 收益率数据，用于计算IC值
        method: 相关性计算方法，支持spearman和pearson
    """

    factor_data: dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算IC值",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: dict[str, Any] = Field(
        ...,
        description="收益率数据，用于计算IC值",
        example={"BTCUSDT": [0.01, 0.02, 0.03], "ETHUSDT": [0.04, 0.05, 0.06]},
    )
    method: str = Field(
        default="spearman",
        description="相关性计算方法，支持spearman和pearson",
        example="spearman",
    )

    @validator("method")
    def validate_method(cls, v: str) -> str:
        """验证计算方法"""
        allowed_methods = ["spearman", "pearson"]
        if v not in allowed_methods:
            msg = f"计算方法必须是以下之一: {allowed_methods}"
            raise ValueError(msg)
        return v


class FactorIRRequest(BaseSchema):
    """
    计算因子IR请求模型

    Attributes:
        factor_data: 因子数据，用于计算IR值
        return_data: 收益率数据，用于计算IR值
        method: 相关性计算方法，支持spearman和pearson
    """

    factor_data: dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算IR值",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: dict[str, Any] = Field(
        ...,
        description="收益率数据，用于计算IR值",
        example={"BTCUSDT": [0.01, 0.02, 0.03], "ETHUSDT": [0.04, 0.05, 0.06]},
    )
    method: str = Field(
        default="spearman",
        description="相关性计算方法，支持spearman和pearson",
        example="spearman",
    )


class FactorGroupAnalysisRequest(BaseSchema):
    """
    因子分组分析请求模型

    Attributes:
        factor_data: 因子数据，用于分组分析
        return_data: 收益率数据，用于分组分析
        n_groups: 分组数量，将标的按因子值分为多少组
    """

    factor_data: dict[str, Any] = Field(
        ...,
        description="因子数据，用于分组分析",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: dict[str, Any] = Field(
        ...,
        description="收益率数据，用于分组分析",
        example={"BTCUSDT": [0.01, 0.02, 0.03], "ETHUSDT": [0.04, 0.05, 0.06]},
    )
    n_groups: int = Field(
        default=5,
        ge=2,
        le=10,
        description="分组数量，将标的按因子值分为多少组",
        example=5,
    )


class FactorMonotonicityRequest(BaseSchema):
    """
    因子单调性检验请求模型

    Attributes:
        factor_data: 因子数据，用于检验单调性
        return_data: 收益率数据，用于检验单调性
        n_groups: 分组数量
    """

    factor_data: dict[str, Any] = Field(
        ...,
        description="因子数据，用于检验单调性",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: dict[str, Any] = Field(
        ...,
        description="收益率数据，用于检验单调性",
        example={"BTCUSDT": [0.01, 0.02, 0.03], "ETHUSDT": [0.04, 0.05, 0.06]},
    )
    n_groups: int = Field(
        default=5,
        ge=2,
        le=10,
        description="分组数量",
    )


class FactorStabilityRequest(BaseSchema):
    """
    因子稳定性检验请求模型

    Attributes:
        factor_data: 因子数据，用于检验稳定性
        window: 滚动窗口大小
    """

    factor_data: dict[str, Any] = Field(
        ...,
        description="因子数据，用于检验稳定性",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    window: int = Field(
        default=20,
        ge=5,
        le=252,
        description="滚动窗口大小",
    )


class FactorData(BaseSchema):
    """
    因子数据模型

    Attributes:
        date: 日期
        instrument: 标的
        value: 因子值
    """

    date: str = Field(..., description="日期", example="2023-01-01")
    instrument: str = Field(..., description="标的", example="BTCUSDT")
    value: float = Field(..., description="因子值", example=0.5)


class FactorResult(BaseSchema):
    """
    因子计算结果模型

    Attributes:
        factor_name: 因子名称
        data: 因子数据列表
        shape: 数据形状
    """

    factor_name: str = Field(..., description="因子名称", example="my_factor")
    data: list[FactorData] = Field(..., description="因子数据列表")
    shape: list[int] = Field(..., description="数据形状", example=[100, 5])


class FactorInfo(BaseSchema):
    """
    因子信息模型

    Attributes:
        factor_name: 因子名称
        expression: 因子表达式
        description: 因子描述
    """

    factor_name: str = Field(..., description="因子名称", example="my_factor")
    expression: str = Field(..., description="因子表达式", example="close - open")
    description: str | None = Field(None, description="因子描述")
