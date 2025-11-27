# 因子计算服务API数据模型

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ApiResponse(BaseModel):
    """
    API响应通用模型
    """
    code: int = Field(..., description="响应码，0表示成功，非0表示失败")
    message: str = Field(..., description="响应消息")
    data: Dict[str, Any] = Field(default_factory=dict, description="响应数据")


class FactorAddRequest(BaseModel):
    """
    添加因子请求模型
    """
    factor_name: str = Field(..., description="因子名称")
    expression: str = Field(..., description="因子表达式")


class FactorCalculateRequest(BaseModel):
    """
    计算因子请求模型
    """
    factor_name: str = Field(..., description="因子名称")
    instruments: List[str] = Field(..., description="标的列表")
    start_time: str = Field(..., description="开始时间，格式：YYYY-MM-DD")
    end_time: str = Field(..., description="结束时间，格式：YYYY-MM-DD")
    freq: str = Field(default="day", description="频率，默认为日线")


class FactorCalculateMultiRequest(BaseModel):
    """
    计算多个因子请求模型
    """
    factor_names: List[str] = Field(..., description="因子名称列表")
    instruments: List[str] = Field(..., description="标的列表")
    start_time: str = Field(..., description="开始时间，格式：YYYY-MM-DD")
    end_time: str = Field(..., description="结束时间，格式：YYYY-MM-DD")
    freq: str = Field(default="day", description="频率，默认为日线")


class FactorValidateRequest(BaseModel):
    """
    验证因子表达式请求模型
    """
    expression: str = Field(..., description="因子表达式")


class FactorCorrelationRequest(BaseModel):
    """
    计算因子相关性请求模型
    """
    factor_data: Dict[str, Any] = Field(..., description="因子数据")


class FactorStatsRequest(BaseModel):
    """
    获取因子统计信息请求模型
    """
    factor_data: Dict[str, Any] = Field(..., description="因子数据")


class FactorICRequest(BaseModel):
    """
    计算因子IC请求模型
    """
    factor_data: Dict[str, Any] = Field(..., description="因子数据")
    return_data: Dict[str, Any] = Field(..., description="收益率数据")
    method: str = Field(default="spearman", description="相关性计算方法")


class FactorIRRequest(BaseModel):
    """
    计算因子IR请求模型
    """
    factor_data: Dict[str, Any] = Field(..., description="因子数据")
    return_data: Dict[str, Any] = Field(..., description="收益率数据")
    method: str = Field(default="spearman", description="相关性计算方法")


class FactorGroupAnalysisRequest(BaseModel):
    """
    因子分组分析请求模型
    """
    factor_data: Dict[str, Any] = Field(..., description="因子数据")
    return_data: Dict[str, Any] = Field(..., description="收益率数据")
    n_groups: int = Field(default=5, description="分组数量")


class FactorMonotonicityRequest(BaseModel):
    """
    因子单调性检验请求模型
    """
    factor_data: Dict[str, Any] = Field(..., description="因子数据")
    return_data: Dict[str, Any] = Field(..., description="收益率数据")
    n_groups: int = Field(default=5, description="分组数量")


class FactorStabilityRequest(BaseModel):
    """
    因子稳定性检验请求模型
    """
    factor_data: Dict[str, Any] = Field(..., description="因子数据")
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
