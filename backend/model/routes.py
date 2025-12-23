# 模型训练服务API路由

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from .schemas import (ApiResponse, ModelConfigRequest, ModelDeleteRequest,
                      ModelEvaluateRequest, ModelListRequest, ModelLoadRequest,
                      ModelPredictRequest, ModelSaveRequest, ModelTrainRequest)
from .service import ModelService

# 创建API路由实例
router = APIRouter()

# 创建模型服务实例
model_service = ModelService()

# 创建模型训练API路由子路由
router_model = APIRouter(prefix="/api/model", tags=["model-training"])


@router_model.get("/list", response_model=ApiResponse)
def get_model_list():
    """
    获取所有支持的模型类型列表
    
    Returns:
        ApiResponse: API响应，包含模型类型列表
    """
    try:
        logger.info("获取模型列表请求")
        
        # 获取模型列表
        models = model_service.get_model_list()
        
        logger.info(f"成功获取模型列表，共 {len(models)} 个模型类型")
        
        return ApiResponse(
            code=0,
            message="获取模型列表成功",
            data={"models": models}
        )
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_model.get("/saved", response_model=ApiResponse)
def get_saved_models():
    """
    获取所有保存的模型列表
    
    Returns:
        ApiResponse: API响应，包含保存的模型列表
    """
    try:
        logger.info("获取保存的模型列表请求")
        
        # 获取保存的模型列表
        saved_models = model_service.list_saved_models()
        
        logger.info(f"成功获取保存的模型列表，共 {len(saved_models)} 个模型")
        
        return ApiResponse(
            code=0,
            message="获取保存的模型列表成功",
            data={"saved_models": saved_models}
        )
    except Exception as e:
        logger.error(f"获取保存的模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_model.post("/train", response_model=ApiResponse)
def train_model(request: ModelTrainRequest):
    """
    训练模型
    
    Args:
        request: 模型训练请求参数，包含模型配置、数据集配置和训练器配置
        
    Returns:
        ApiResponse: API响应，包含模型训练结果
    """
    try:
        logger.info("模型训练请求")
        
        # 训练模型
        result = model_service.train_model(
            model_config=request.model_config,
            dataset_config=request.dataset_config,
            trainer_config=request.trainer_config
        )
        
        logger.info(f"模型训练完成，结果: {result}")
        
        return ApiResponse(
            code=0,
            message="模型训练成功",
            data=result
        )
    except Exception as e:
        logger.error(f"模型训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_model.post("/evaluate", response_model=ApiResponse)
def evaluate_model(request: ModelEvaluateRequest):
    """
    评估模型
    
    Args:
        request: 模型评估请求参数，包含模型名称和数据集配置
        
    Returns:
        ApiResponse: API响应，包含模型评估结果
    """
    try:
        logger.info(f"模型评估请求，模型名称: {request.model_name}")
        
        # 评估模型
        result = model_service.evaluate_model(
            model_name=request.model_name,
            dataset_config=request.dataset_config
        )
        
        logger.info(f"模型评估完成，结果: {result}")
        
        return ApiResponse(
            code=0,
            message="模型评估成功",
            data=result
        )
    except Exception as e:
        logger.error(f"模型评估失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_model.post("/predict", response_model=ApiResponse)
def predict(request: ModelPredictRequest):
    """
    使用模型进行预测
    
    Args:
        request: 模型预测请求参数，包含模型名称和预测数据
        
    Returns:
        ApiResponse: API响应，包含模型预测结果
    """
    try:
        logger.info(f"模型预测请求，模型名称: {request.model_name}")
        
        # 模型预测
        result = model_service.predict(
            model_name=request.model_name,
            data=request.data
        )
        
        logger.info(f"模型预测完成，结果: {result}")
        
        return ApiResponse(
            code=0,
            message="模型预测成功",
            data=result
        )
    except Exception as e:
        logger.error(f"模型预测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_model.delete("/delete/{model_name}", response_model=ApiResponse)
def delete_model(model_name: str):
    """
    删除模型
    
    Args:
        model_name: 模型名称
        
    Returns:
        ApiResponse: API响应，包含模型删除结果
    """
    try:
        logger.info(f"模型删除请求，模型名称: {model_name}")
        
        # 删除模型
        result = model_service.delete_model(model_name)
        
        if result:
            logger.info(f"模型删除成功，模型名称: {model_name}")
            return ApiResponse(
                code=0,
                message="模型删除成功",
                data={"model_name": model_name, "result": result}
            )
        else:
            logger.warning(f"模型删除失败，模型名称: {model_name}")
            return ApiResponse(
                code=1,
                message="模型删除失败",
                data={"model_name": model_name, "result": result}
            )
    except Exception as e:
        logger.error(f"模型删除失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_model.post("/config", response_model=ApiResponse)
def create_model_config(request: ModelConfigRequest):
    """
    创建模型配置
    
    Args:
        request: 模型配置请求参数，包含模型类型和参数
        
    Returns:
        ApiResponse: API响应，包含模型配置
    """
    try:
        logger.info(f"创建模型配置请求，模型类型: {request.model_type}")
        
        # 创建模型配置
        model_config = model_service.create_model_config(
            model_type=request.model_type,
            params=request.params
        )
        
        if model_config:
            logger.info(f"模型配置创建成功，模型类型: {request.model_type}")
            return ApiResponse(
                code=0,
                message="模型配置创建成功",
                data={"model_config": model_config}
            )
        else:
            logger.error(f"模型配置创建失败，模型类型: {request.model_type}")
            return ApiResponse(
                code=1,
                message="模型配置创建失败",
                data={}
            )
    except Exception as e:
        logger.error(f"模型配置创建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_model.get("/config/{model_name}", response_model=ApiResponse)
def get_model_config(model_name: str):
    """
    获取模型配置
    
    Args:
        model_name: 模型名称
        
    Returns:
        ApiResponse: API响应，包含模型配置
    """
    try:
        logger.info(f"获取模型配置请求，模型名称: {model_name}")
        
        # 获取模型配置
        model_config = model_service.get_model_config(model_name)
        
        if model_config:
            logger.info(f"模型配置获取成功，模型名称: {model_name}")
            return ApiResponse(
                code=0,
                message="模型配置获取成功",
                data={"model_config": model_config}
            )
        else:
            logger.warning(f"模型配置获取失败，模型名称: {model_name}")
            return ApiResponse(
                code=1,
                message="模型配置获取失败",
                data={}
            )
    except Exception as e:
        logger.error(f"模型配置获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册模型训练API路由
router.include_router(router_model)
