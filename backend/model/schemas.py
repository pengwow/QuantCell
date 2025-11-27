# 模型训练服务API数据模型

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ApiResponse(BaseModel):
    """
    API响应通用模型
    """
    code: int = Field(..., description="响应码，0表示成功，非0表示失败")
    message: str = Field(..., description="响应消息")
    data: Dict[str, Any] = Field(default_factory=dict, description="响应数据")


class ModelListRequest(BaseModel):
    """
    获取模型列表请求模型
    """
    pass


class ModelTrainRequest(BaseModel):
    """
    模型训练请求模型
    """
    model_parameters: Dict[str, Any] = Field(..., description="模型配置")
    dataset_config: Dict[str, Any] = Field(..., description="数据集配置")
    trainer_config: Dict[str, Any] = Field(..., description="训练器配置")


class ModelEvaluateRequest(BaseModel):
    """
    模型评估请求模型
    """
    model_name: str = Field(..., description="模型名称")
    dataset_config: Dict[str, Any] = Field(..., description="数据集配置")


class ModelPredictRequest(BaseModel):
    """
    模型预测请求模型
    """
    model_name: str = Field(..., description="模型名称")
    data: Dict[str, Any] = Field(..., description="预测数据")


class ModelSaveRequest(BaseModel):
    """
    模型保存请求模型
    """
    model_name: str = Field(..., description="模型名称")
    model_data: bytes = Field(..., description="模型数据")


class ModelLoadRequest(BaseModel):
    """
    模型加载请求模型
    """
    model_name: str = Field(..., description="模型名称")


class ModelDeleteRequest(BaseModel):
    """
    模型删除请求模型
    """
    model_name: str = Field(..., description="模型名称")


class ModelConfigRequest(BaseModel):
    """
    模型配置请求模型
    """
    model_type: str = Field(..., description="模型类型")
    params: Dict[str, Any] = Field(..., description="模型参数")


class ModelListResponse(BaseModel):
    """
    模型列表响应模型
    """
    models: List[str] = Field(..., description="模型类型列表")


class ModelTrainResponse(BaseModel):
    """
    模型训练响应模型
    """
    model_name: str = Field(..., description="模型名称")
    status: str = Field(..., description="训练状态")
    message: str = Field(..., description="训练消息")


class ModelEvaluateResponse(BaseModel):
    """
    模型评估响应模型
    """
    model_name: str = Field(..., description="模型名称")
    status: str = Field(..., description="评估状态")
    metrics: Dict[str, float] = Field(..., description="评估指标")


class ModelPredictResponse(BaseModel):
    """
    模型预测响应模型
    """
    model_name: str = Field(..., description="模型名称")
    status: str = Field(..., description="预测状态")
    predictions: List[float] = Field(..., description="预测结果")


class ModelConfig(BaseModel):
    """
    模型配置模型
    """
    model_type: str = Field(..., description="模型类型")
    params: Dict[str, Any] = Field(..., description="模型参数")
    model_name: Optional[str] = Field(None, description="模型名称")


class DatasetConfig(BaseModel):
    """
    数据集配置模型
    """
    handler: Dict[str, Any] = Field(..., description="数据处理配置")
    segments: Dict[str, Any] = Field(..., description="数据分段配置")


class TrainerConfig(BaseModel):
    """
    训练器配置模型
    """
    class_name: str = Field(..., description="训练器类名")
    params: Dict[str, Any] = Field(..., description="训练器参数")
