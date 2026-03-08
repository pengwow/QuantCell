"""
AI模型配置API路由

提供AI大模型厂商配置的RESTful API端点。

路由前缀:
    - /api/ai-models: AI模型配置管理

标签: ai-model-config

包含端点:
    - GET /api/ai-models: 获取配置列表
    - POST /api/ai-models: 创建配置
    - GET /api/ai-models/providers: 获取支持的厂商列表
    - POST /api/ai-models/check: 检查模型可用性
    - GET /api/ai-models/{id}: 获取单个配置
    - PUT /api/ai-models/{id}: 更新配置
    - DELETE /api/ai-models/{id}: 删除配置
    - GET /api/ai-models/{id}/models: 获取可用模型列表

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-02
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request
from loguru import logger

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required_sync

from .models import AIModelBusiness
from .schemas import (
    AIModelCheckRequest,
    AIModelCheckResponse,
    AIModelCreate,
    AIModelListResponse,
    AIModelQueryParams,
    AIModelResponse,
    AIModelUpdate,
)
from .services import AIModelService

# 创建AI模型配置API路由
router = APIRouter(prefix="/api/ai-models", tags=["ai-model-config"])


@router.get("/", response_model=ApiResponse)
@jwt_auth_required_sync
def get_ai_models(
    request: Request,
    page: int = Query(1, ge=1, description="页码，从1开始"),
    limit: int = Query(10, ge=1, le=100, description="每页记录数"),
    provider: Optional[str] = Query(None, description="按厂商筛选"),
    is_enabled: Optional[bool] = Query(None, description="按启用状态筛选"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序顺序，asc或desc"),
):
    """获取AI模型配置列表

    Args:
        request: FastAPI请求对象
        page: 页码，从1开始
        limit: 每页记录数
        provider: 按厂商筛选
        is_enabled: 按启用状态筛选
        sort_by: 排序字段
        sort_order: 排序顺序

    Returns:
        ApiResponse: 包含配置列表和分页信息的响应

    Responses:
        200: 成功获取配置列表
        401: 未授权访问
        500: 获取配置列表失败
    """
    try:
        logger.info(f"获取AI模型配置列表: page={page}, limit={limit}, provider={provider}")

        result = AIModelBusiness.list(
            page=page,
            limit=limit,
            provider=provider,
            is_enabled=is_enabled,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return ApiResponse(
            code=0,
            message="获取AI模型配置列表成功",
            data=result,
        )
    except Exception as e:
        logger.error(f"获取AI模型配置列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=ApiResponse)
@jwt_auth_required_sync
def create_ai_model(request: Request, config: AIModelCreate):
    """创建AI模型配置

    Args:
        request: FastAPI请求对象
        config: 配置创建请求体

    Returns:
        ApiResponse: 包含创建结果的响应

    Responses:
        200: 创建成功
        400: 请求数据格式错误
        401: 未授权访问
        500: 创建失败
    """
    try:
        logger.info(f"创建AI模型配置: provider={config.provider}, name={config.name}")

        result = AIModelBusiness.create(
            provider=config.provider,
            name=config.name,
            api_key=config.api_key,
            api_host=config.api_host,
            models=config.models,
            is_default=config.is_default,
            is_enabled=config.is_enabled,
            proxy_enabled=config.proxy_enabled,
            proxy_url=config.proxy_url,
            proxy_username=config.proxy_username,
            proxy_password=config.proxy_password,
        )

        if result:
            return ApiResponse(
                code=0,
                message="创建AI模型配置成功",
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message="创建AI模型配置失败",
                data=None,
            )
    except Exception as e:
        logger.error(f"创建AI模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers", response_model=ApiResponse)
@jwt_auth_required_sync
def get_supported_providers(request: Request):
    """获取支持的AI厂商列表

    Args:
        request: FastAPI请求对象

    Returns:
        ApiResponse: 包含支持的厂商列表的响应

    Responses:
        200: 成功获取厂商列表
        401: 未授权访问
    """
    try:
        logger.info("获取支持的AI厂商列表")

        providers = AIModelService.get_supported_providers()

        return ApiResponse(
            code=0,
            message="获取支持的AI厂商列表成功",
            data={"providers": providers},
        )
    except Exception as e:
        logger.error(f"获取支持的AI厂商列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check", response_model=ApiResponse)
@jwt_auth_required_sync
async def check_ai_model_availability(
    request: Request,
    check_request: AIModelCheckRequest,
):
    """检查AI模型可用性

    通过API Key和API Host验证AI厂商服务是否可用。

    Args:
        request: FastAPI请求对象
        check_request: 可用性检查请求体

    Returns:
        ApiResponse: 包含检查结果的响应

    Responses:
        200: 检查完成
        400: 请求数据格式错误
        401: 未授权访问
        500: 检查失败

    Request Example:
        {
            "provider": "openai",
            "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxx",
            "api_host": "https://api.openai.com"
        }

    Response Example:
        {
            "code": 0,
            "message": "检查完成",
            "data": {
                "available": true,
                "message": "OpenAI服务可用",
                "models": [
                    {"id": "gpt-4", "name": "gpt-4", "description": "...", "provider": "openai"}
                ]
            }
        }
    """
    try:
        logger.info(f"检查AI模型可用性: provider={check_request.provider}")

        result = await AIModelService.check_provider_availability(
            provider=check_request.provider,
            api_key=check_request.api_key,
            api_host=check_request.api_host,
            proxy_enabled=check_request.proxy_enabled,
            proxy_url=check_request.proxy_url,
            proxy_username=check_request.proxy_username,
            proxy_password=check_request.proxy_password,
        )

        return ApiResponse(
            code=0,
            message="检查完成",
            data=result,
        )
    except Exception as e:
        logger.error(f"检查AI模型可用性失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{model_id}", response_model=ApiResponse)
@jwt_auth_required_sync
def get_ai_model(
    request: Request,
    model_id: int = Path(..., ge=1, description="配置ID"),
):
    """获取单个AI模型配置

    Args:
        request: FastAPI请求对象
        model_id: 配置ID

    Returns:
        ApiResponse: 包含配置信息的响应

    Responses:
        200: 成功获取配置
        401: 未授权访问
        404: 配置不存在
        500: 获取配置失败
    """
    try:
        logger.info(f"获取AI模型配置: id={model_id}")

        result = AIModelBusiness.get_by_id(model_id)

        if result:
            return ApiResponse(
                code=0,
                message="获取AI模型配置成功",
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message="AI模型配置不存在",
                data=None,
            )
    except Exception as e:
        logger.error(f"获取AI模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{model_id}", response_model=ApiResponse)
@jwt_auth_required_sync
def update_ai_model(
    request: Request,
    config: AIModelUpdate,
    model_id: int = Path(..., ge=1, description="配置ID"),
):
    """更新AI模型配置

    Args:
        request: FastAPI请求对象
        config: 配置更新请求体
        model_id: 配置ID

    Returns:
        ApiResponse: 包含更新结果的响应

    Responses:
        200: 更新成功
        400: 请求数据格式错误
        401: 未授权访问
        404: 配置不存在
        500: 更新失败
    """
    try:
        logger.info(f"更新AI模型配置: id={model_id}")

        result = AIModelBusiness.update(
            model_id=model_id,
            provider=config.provider,
            name=config.name,
            api_key=config.api_key,
            api_host=config.api_host,
            models=config.models,
            is_default=config.is_default,
            is_enabled=config.is_enabled,
            proxy_enabled=config.proxy_enabled,
            proxy_url=config.proxy_url,
            proxy_username=config.proxy_username,
            proxy_password=config.proxy_password,
        )

        if result:
            return ApiResponse(
                code=0,
                message="更新AI模型配置成功",
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message="AI模型配置不存在或更新失败",
                data=None,
            )
    except Exception as e:
        logger.error(f"更新AI模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{model_id}", response_model=ApiResponse)
@jwt_auth_required_sync
def delete_ai_model(
    request: Request,
    model_id: int = Path(..., ge=1, description="配置ID"),
):
    """删除AI模型配置

    Args:
        request: FastAPI请求对象
        model_id: 配置ID

    Returns:
        ApiResponse: 包含删除结果的响应

    Responses:
        200: 删除成功
        401: 未授权访问
        404: 配置不存在
        500: 删除失败
    """
    try:
        logger.info(f"删除AI模型配置: id={model_id}")

        success = AIModelBusiness.delete(model_id)

        if success:
            return ApiResponse(
                code=0,
                message="删除AI模型配置成功",
                data={"id": model_id},
            )
        else:
            return ApiResponse(
                code=1,
                message="AI模型配置不存在或删除失败",
                data=None,
            )
    except Exception as e:
        logger.error(f"删除AI模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{model_id}/models", response_model=ApiResponse)
@jwt_auth_required_sync
async def get_available_models(
    request: Request,
    model_id: int = Path(..., ge=1, description="配置ID"),
):
    """获取配置的可用模型列表

    从厂商API获取当前配置可用的模型列表。

    Args:
        request: FastAPI请求对象
        model_id: 配置ID

    Returns:
        ApiResponse: 包含可用模型列表的响应

    Responses:
        200: 成功获取模型列表
        401: 未授权访问
        404: 配置不存在
        500: 获取失败
    """
    try:
        logger.info(f"获取可用模型列表: id={model_id}")

        # 获取配置信息
        config = AIModelBusiness.get_by_id(model_id, include_api_key=True)
        if not config:
            return ApiResponse(
                code=1,
                message="AI模型配置不存在",
                data=None,
            )

        # 获取API密钥
        api_key = config.get("api_key")
        if not api_key:
            return ApiResponse(
                code=1,
                message="配置中没有API密钥",
                data=None,
            )

        # 获取可用模型列表
        models = await AIModelService.fetch_available_models(
            provider=config["provider"],
            api_key=api_key,
            api_host=config.get("api_host"),
        )

        return ApiResponse(
            code=0,
            message="获取可用模型列表成功",
            data={
                "provider": config["provider"],
                "models": models,
                "total": len(models),
            },
        )
    except Exception as e:
        logger.error(f"获取可用模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

