# 模型训练服务API数据模型

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# 导入统一的ApiResponse模型
from common.schemas import ApiResponse


class ModelListRequest(BaseModel):
    """
    获取模型列表请求模型
    """
    model_type: Optional[str] = Field(
        None,
        description="模型类型，可选",
        example="xgboost",
    )
    page: int = Field(
        default=1,
        description="页码，从1开始",
        example=1,
        ge=1,
    )
    limit: int = Field(
        default=10,
        description="每页记录数",
        example=10,
        ge=1,
        le=100,
    )


class ModelParameters(BaseModel):
    """
    模型参数模型
    """
    model_type: str = Field(
        ...,
        description="模型类型",
        example="xgboost",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="模型参数",
        example={"n_estimators": 100, "max_depth": 5},
    )
    name: Optional[str] = Field(
        None,
        description="模型名称，可选",
        example="my_model",
    )


class DatasetConfig(BaseModel):
    """
    数据集配置模型
    """
    handler: Dict[str, Any] = Field(
        ...,
        description="数据处理配置",
        example={"name": "csv_handler", "params": {"file_path": "/path/to/data.csv"}},
    )
    segments: Dict[str, Any] = Field(
        ...,
        description="数据分段配置",
        example={"train": "train_data", "test": "test_data"},
    )


class TrainerConfig(BaseModel):
    """
    训练器配置模型
    """
    class_name: str = Field(
        ...,
        description="训练器类名",
        example="Trainer",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="训练器参数",
        example={"epochs": 10, "batch_size": 32},
    )


class ModelTrainRequest(BaseModel):
    """
    模型训练请求模型
    """
    model_parameters: ModelParameters = Field(
        ...,
        description="模型配置",
        example={
            "model_type": "xgboost",
            "params": {"n_estimators": 100, "max_depth": 5},
            "name": "my_model"
        },
    )
    dataset_config: DatasetConfig = Field(
        ...,
        description="数据集配置",
        example={
            "handler": {"name": "csv_handler", "params": {"file_path": "/path/to/data.csv"}},
            "segments": {"train": "train_data", "test": "test_data"}
        },
    )
    trainer_config: TrainerConfig = Field(
        ...,
        description="训练器配置",
        example={
            "class_name": "Trainer",
            "params": {"epochs": 10, "batch_size": 32}
        },
    )


class ModelEvaluateRequest(BaseModel):
    """
    模型评估请求模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )
    dataset_config: DatasetConfig = Field(
        ...,
        description="数据集配置",
        example={
            "handler": {"name": "csv_handler", "params": {"file_path": "/path/to/test_data.csv"}},
            "segments": {"test": "test_data"}
        },
    )


class ModelPredictRequest(BaseModel):
    """
    模型预测请求模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )
    data: Dict[str, Any] = Field(
        ...,
        description="预测数据",
        example={"features": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]},
    )


class ModelSaveRequest(BaseModel):
    """
    模型保存请求模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )
    model_data: bytes = Field(
        ...,
        description="模型数据",
        example=b"model binary data",
    )


class ModelLoadRequest(BaseModel):
    """
    模型加载请求模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )


class ModelDeleteRequest(BaseModel):
    """
    模型删除请求模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )


class ModelConfigRequest(BaseModel):
    """
    模型配置请求模型
    """
    model_type: str = Field(
        ...,
        description="模型类型",
        example="xgboost",
    )
    params: Dict[str, Any] = Field(
        ...,
        description="模型参数",
        example={"n_estimators": 100, "max_depth": 5},
    )


class ModelListResponse(BaseModel):
    """
    模型列表响应模型
    """
    models: List[str] = Field(
        ...,
        description="模型类型列表",
        example=["xgboost", "catboost", "random_forest"],
    )


class ModelTrainResponse(BaseModel):
    """
    模型训练响应模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )
    status: str = Field(
        ...,
        description="训练状态",
        example="completed",
    )
    message: str = Field(
        ...,
        description="训练消息",
        example="模型训练成功",
    )
    train_time: Optional[str] = Field(
        None,
        description="训练时间，可选",
        example="2023-01-01 00:00:00",
    )


class ModelEvaluateResponse(BaseModel):
    """
    模型评估响应模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )
    status: str = Field(
        ...,
        description="评估状态",
        example="completed",
    )
    metrics: Dict[str, float] = Field(
        ...,
        description="评估指标",
        example={"accuracy": 0.95, "precision": 0.92, "recall": 0.90},
    )


class ModelPredictResponse(BaseModel):
    """
    模型预测响应模型
    """
    model_name: str = Field(
        ...,
        description="模型名称",
        example="my_model",
    )
    status: str = Field(
        ...,
        description="预测状态",
        example="completed",
    )
    predictions: List[float] = Field(
        ...,
        description="预测结果",
        example=[0.1, 0.9, 0.8, 0.2],
    )
    predict_time: Optional[str] = Field(
        None,
        description="预测时间，可选",
        example="2023-01-01 00:00:00",
    )


class ModelConfig(BaseModel):
    """
    模型配置模型
    """
    model_type: str = Field(
        ...,
        description="模型类型",
        example="xgboost",
    )
    params: Dict[str, Any] = Field(
        ...,
        description="模型参数",
        example={"n_estimators": 100, "max_depth": 5},
    )
    model_name: Optional[str] = Field(
        None,
        description="模型名称，可选",
        example="my_model",
    )
