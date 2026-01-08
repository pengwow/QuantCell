# 因子计算服务API数据模型

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# 导入统一的ApiResponse模型
from common.schemas import ApiResponse


class FactorAddRequest(BaseModel):
    """
    添加因子请求模型
    """
    factor_name: str = Field(
        ...,
        description="因子名称",
        example="my_factor"
    )
    expression: str = Field(
        ...,
        description="因子表达式，用于计算因子值",
        example="close - open"
    )


class FactorCalculateRequest(BaseModel):
    """
    计算因子请求模型
    """
    factor_name: str = Field(
        ...,
        description="因子名称",
        example="my_factor"
    )
    instruments: List[str] = Field(
        ...,
        description="标的列表，如股票代码、加密货币交易对等",
        example=["BTCUSDT", "ETHUSDT"]
    )
    start_time: str = Field(
        ...,
        description="开始时间，格式：YYYY-MM-DD",
        example="2023-01-01"
    )
    end_time: str = Field(
        ...,
        description="结束时间，格式：YYYY-MM-DD",
        example="2023-12-31"
    )
    freq: str = Field(
        default="day",
        description="频率，默认为日线",
        example="day"
    )


class FactorCalculateMultiRequest(BaseModel):
    """
    计算多个因子请求模型
    """
    factor_names: List[str] = Field(
        ...,
        description="因子名称列表，用于批量计算多个因子",
        example=["my_factor1", "my_factor2"]
    )
    instruments: List[str] = Field(
        ...,
        description="标的列表，如股票代码、加密货币交易对等",
        example=["BTCUSDT", "ETHUSDT"]
    )
    start_time: str = Field(
        ...,
        description="开始时间，格式：YYYY-MM-DD",
        example="2023-01-01"
    )
    end_time: str = Field(
        ...,
        description="结束时间，格式：YYYY-MM-DD",
        example="2023-12-31"
    )
    freq: str = Field(
        default="day",
        description="频率，默认为日线",
        example="day"
    )


class FactorValidateRequest(BaseModel):
    """
    验证因子表达式请求模型
    """
    expression: str = Field(
        ...,
        description="因子表达式，用于验证其语法正确性",
        example="close - open"
    )


class FactorCorrelationRequest(BaseModel):
    """
    计算因子相关性请求模型
    """
    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，包含不同因子的计算结果",
        example={
            "factor1": {"BTCUSDT": [0.1, 0.2, 0.3], "ETHUSDT": [0.4, 0.5, 0.6]},
            "factor2": {"BTCUSDT": [0.7, 0.8, 0.9], "ETHUSDT": [1.0, 1.1, 1.2]}
        }
    )


class FactorStatsRequest(BaseModel):
    """
    获取因子统计信息请求模型
    """
    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算统计信息",
        example={
            "factor1": {"BTCUSDT": [0.1, 0.2, 0.3], "ETHUSDT": [0.4, 0.5, 0.6]}
        }
    )


class FactorICRequest(BaseModel):
    """
    计算因子IC请求模型
    """
    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算IC值",
        example={
            "factor1": {"BTCUSDT": [0.1, 0.2, 0.3], "ETHUSDT": [0.4, 0.5, 0.6]}
        }
    )
    return_data: Dict[str, Any] = Field(
        ...,
        description="收益率数据，用于计算IC值",
        example={
            "BTCUSDT": [0.01, 0.02, 0.03],
            "ETHUSDT": [0.04, 0.05, 0.06]
        }
    )
    method: str = Field(
        default="spearman",
        description="相关性计算方法，支持spearman和pearson",
        example="spearman"
    )


class FactorIRRequest(BaseModel):
    """
    计算因子IR请求模型
    """
    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于计算IR值",
        example={
            "factor1": {"BTCUSDT": [0.1, 0.2, 0.3], "ETHUSDT": [0.4, 0.5, 0.6]}
        }
    )
    return_data: Dict[str, Any] = Field(
        ...,
        description="收益率数据，用于计算IR值",
        example={
            "BTCUSDT": [0.01, 0.02, 0.03],
            "ETHUSDT": [0.04, 0.05, 0.06]
        }
    )
    method: str = Field(
        default="spearman",
        description="相关性计算方法，支持spearman和pearson",
        example="spearman"
    )


class FactorGroupAnalysisRequest(BaseModel):
    """
    因子分组分析请求模型
    """
    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于分组分析",
        example={
            "factor1": {"BTCUSDT": [0.1, 0.2, 0.3], "ETHUSDT": [0.4, 0.5, 0.6]}
        }
    )
    return_data: Dict[str, Any] = Field(
        ...,
        description="收益率数据，用于分组分析",
        example={
            "BTCUSDT": [0.01, 0.02, 0.03],
            "ETHUSDT": [0.04, 0.05, 0.06]
        }
    )
    n_groups: int = Field(
        default=5,
        description="分组数量，将标的按因子值分为多少组",
        example=5
    )


class FactorMonotonicityRequest(BaseModel):
    """
    因子单调性检验请求模型
    """
    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于检验单调性",
        example={
            "factor1": {"BTCUSDT": [0.1, 0.2, 0.3], "ETHUSDT": [0.4, 0.5, 0.6]}
        }
    )
    return_data: Dict[str, Any] = Field(
        ...,
        description="收益率数据，用于检验单调性",
        example={
            "BTCUSDT": [0.01, 0.02, 0.03],
            "ETHUSDT": [0.04, 0.05, 0.06]
        }
    )
    n_groups: int = Field(default=5, description="分组数量")


class FactorStabilityRequest(BaseModel):
    """
    因子稳定性检验请求模型
    """
    factor_data: Dict[str, Any] = Field(
        ...,
        description="因子数据，用于检验稳定性",
        example={
            "factor1": {"BTCUSDT": [0.1, 0.2, 0.3], "ETHUSDT": [0.4, 0.5, 0.6]}
        }
    )
    window: int = Field(default=20, description="滚动窗口大小")


class FactorData(BaseModel):
    """
    因子数据模型
    """
    date: str = Field(..., description="日期")
    instrument: str = Field(..., description="标的")
    value: float = Field(..., description="因子值")


class FactorResult(BaseModel):
    """
    因子计算结果模型
    """
    factor_name: str = Field(..., description="因子名称")
    data: List[FactorData] = Field(..., description="因子数据列表")
    shape: List[int] = Field(..., description="数据形状")


class FactorInfo(BaseModel):
    """
    因子信息模型
    """
    factor_name: str = Field(..., description="因子名称")
    expression: str = Field(..., description="因子表达式")
    description: Optional[str] = Field(None, description="因子描述")
