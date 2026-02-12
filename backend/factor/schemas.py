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
    - 频率：day, week, month
    - 计算方法：spearman, pearson

作者: QuantCell Team
创建日期: 2024-01-01
"""

from typing import Any, Dict, List, Optional

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
            raise ValueError("因子名称不能为空")
        return v.strip()

    @validator("expression")
    def validate_expression(cls, v: str) -> str:
        """验证因子表达式"""
        if not v.strip():
            raise ValueError("因子表达式不能为空")
        return v.strip()


class FactorCalculateRequest(BaseSchema):
    """
    计算因子请求模型

    Attributes:
        factor_name: 因子名称
        instruments: 标的列表，如股票代码、加密货币交易对等
        start_time: 开始时间，格式：YYYY-MM-DD
        end_time: 结束时间，格式：YYYY-MM-DD
        freq: 频率，默认为日线
    """

    factor_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="因子名称",
        example="my_factor",
    )
    instruments: List[str] = Field(
        ...,
        min_items=1,
        description="标的列表，如股票代码、加密货币交易对等",
        example=["BTCUSDT", "ETHUSDT"],
    )
    start_time: str = Field(
        ...,
        description="开始时间，格式：YYYY-MM-DD",
        example="2023-01-01",
    )
    end_time: str = Field(
        ...,
        description="结束时间，格式：YYYY-MM-DD",
        example="2023-12-31",
    )
    freq: str = Field(
        default="day",
        description="频率，默认为日线",
        example="day",
    )

    @validator("freq")
    def validate_freq(cls, v: str) -> str:
        """验证频率"""
        allowed_freqs = ["day", "week", "month", "hour", "minute"]
        if v not in allowed_freqs:
            raise ValueError(f"频率必须是以下之一: {allowed_freqs}")
        return v


class FactorCalculateMultiRequest(BaseSchema):
    """
    计算多个因子请求模型

    Attributes:
        factor_names: 因子名称列表，用于批量计算多个因子
        instruments: 标的列表，如股票代码、加密货币交易对等
        start_time: 开始时间，格式：YYYY-MM-DD
        end_time: 结束时间，格式：YYYY-MM-DD
        freq: 频率，默认为日线
    """

    factor_names: List[str] = Field(
        ...,
        min_items=1,
        description="因子名称列表，用于批量计算多个因子",
        example=["my_factor1", "my_factor2"],
    )
    instruments: List[str] = Field(
        ...,
        min_items=1,
        description="标的列表，如股票代码、加密货币交易对等",
        example=["BTCUSDT", "ETHUSDT"],
    )
    start_time: str = Field(
        ...,
        description="开始时间，格式：YYYY-MM-DD",
        example="2023-01-01",
    )
    end_time: str = Field(
        ...,
        description="结束时间，格式：YYYY-MM-DD",
        example="2023-12-31",
    )
    freq: str = Field(
        default="day",
        description="频率，默认为日线",
        example="day",
    )


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

    factor_data: Dict[str, Any] = Field(
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

    factor_data: Dict[str, Any] = Field(
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

    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算IC值",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: Dict[str, Any] = Field(
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
            raise ValueError(f"计算方法必须是以下之一: {allowed_methods}")
        return v


class FactorIRRequest(BaseSchema):
    """
    计算因子IR请求模型

    Attributes:
        factor_data: 因子数据，用于计算IR值
        return_data: 收益率数据，用于计算IR值
        method: 相关性计算方法，支持spearman和pearson
    """

    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算IR值",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: Dict[str, Any] = Field(
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

    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于分组分析",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: Dict[str, Any] = Field(
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

    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于检验单调性",
        example={
            "factor1": {
                "BTCUSDT": [0.1, 0.2, 0.3],
                "ETHUSDT": [0.4, 0.5, 0.6],
            }
        },
    )
    return_data: Dict[str, Any] = Field(
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

    factor_data: Dict[str, Any] = Field(
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
    data: List[FactorData] = Field(..., description="因子数据列表")
    shape: List[int] = Field(..., description="数据形状", example=[100, 5])


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
    description: Optional[str] = Field(None, description="因子描述")
