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

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request
from loguru import logger

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required, jwt_auth_required_sync

# 导入系统配置模型
from settings.models import SystemConfigBusiness as SystemConfig

from .schemas import (
    AIModelCheckRequest,
    AIModelCreate,
    AIModelUpdate,
)
from .services import AIModelService

# 创建AI模型配置API路由
router = APIRouter(prefix="/api/ai-models", tags=["ai-model-config"])

# 配置名称常量
AI_MODELS_CONFIG_NAME = "ai_models"


def get_ai_models_from_config() -> Dict[str, Dict[str, Any]]:
    """从系统配置表读取AI模型配置
    
    读取name=ai_models的所有配置项
    
    Returns:
        Dict[str, Dict[str, Any]]: AI模型配置字典，键为配置ID
    """
    try:
        # 获取AI模型配置
        ai_model_configs = SystemConfig.get_name_with_details(AI_MODELS_CONFIG_NAME)
        
        # 调试日志：打印所有配置
        logger.info(f"获取到 {len(ai_model_configs)} 条系统配置")
        for key, config in ai_model_configs.items():
            logger.info(f"配置项: key={key}, name={config.get('name')}, value={config.get('value', '')[:50]}...")
        
        # 确保返回的是字典
        if not isinstance(ai_model_configs, dict):
            logger.error(f"get_name_with_details 返回类型错误: {type(ai_model_configs)}")
            return {}

        providers = ai_model_configs.get('providers', {})
        if providers.get('value'):
            providers['value'] = json.loads(providers.get('value', '[]'))
            ai_model_configs['providers'] = providers
        return ai_model_configs
    except Exception as e:
        logger.error(f"从系统配置读取AI模型失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}


def save_ai_model_to_config(model_id: str, model_data: Dict[str, Any]) -> bool:
    """保存AI模型配置到系统配置表
    
    Args:
        model_id: 模型配置ID
        model_data: 模型配置数据
        
    Returns:
        bool: 是否保存成功
    """
    try:
        success = SystemConfig.set(
            key=model_id,
            value=json.dumps(model_data, ensure_ascii=False),
            description=f"{model_data.get('name', 'AI模型')}配置",
            name=AI_MODELS_CONFIG_NAME
        )
        return success
    except Exception as e:
        logger.error(f"保存AI模型配置失败: {e}")
        return False


def delete_ai_model_from_config(model_id: str) -> bool:
    """从系统配置表删除AI模型配置
    
    Args:
        model_id: 模型配置ID
        
    Returns:
        bool: 是否删除成功
    """
    try:
        # SystemConfig没有delete方法，使用set设置空值
        success = SystemConfig.set(
            key=model_id,
            value="",
            description="",
            name=""
        )
        return success
    except Exception as e:
        logger.error(f"删除AI模型配置失败: {e}")
        return False


@router.get("/", response_model=ApiResponse)
@jwt_auth_required_sync
def get_ai_models(
    request: Request,
    page: int = Query(1, ge=1, description="页码，从1开始"),
    limit: int = Query(10, ge=1, le=100, description="每页记录数"),
    provider: Optional[str] = Query(None, description="按厂商筛选"),
    is_default: Optional[bool] = Query(True, description="按默认配置筛选"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序顺序，asc或desc"),
):
    """获取AI模型配置列表

    从系统配置表读取name=ai_models的配置数据

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

        # 从系统配置表读取AI模型配置
        all_models = get_ai_models_from_config()
        
        # 筛选
        filtered_models = all_models
        if provider:
            filtered_models = [m for m in filtered_models.get('providers', [{}]) if m.get("id") == provider]

        if is_default is not None:
            default_provider = all_models.get('default_provider', "")
            if default_provider:
                filtered_models = [m for m in filtered_models if m.get("id") == default_provider.get("value", "")]

        # 排序
        reverse = sort_order.lower() == "desc"
        filtered_models.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)
        
        # 分页
        total = len(filtered_models)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_models = filtered_models[start_idx:end_idx]

        return ApiResponse(
            code=0,
            message="获取AI模型配置列表成功",
            data={
                "items": paginated_models,
                "total": total,
                "page": page,
                "limit": limit,
            },
        )
    except Exception as e:
        logger.error(f"获取AI模型配置列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=ApiResponse)
@jwt_auth_required_sync
def create_ai_model(request: Request, config: AIModelCreate):
    """创建AI模型配置

    保存到系统配置表，name=ai_models

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

        # 生成唯一ID
        import uuid
        model_id = f"{config.provider}_{uuid.uuid4().hex[:8]}"
        
        # 构建模型数据
        model_data = {
            "id": model_id,
            "provider": config.provider,
            "name": config.name,
            "api_key": config.api_key,
            "api_host": config.api_host,
            "models": config.models,
            "is_default": config.is_default,
            "is_enabled": config.is_enabled,
            "proxy_enabled": config.proxy_enabled,
            "proxy_url": config.proxy_url,
            "proxy_username": config.proxy_username,
            "proxy_password": config.proxy_password,
            "created_at": str(uuid.uuid1()),  # 使用时间戳
        }
        
        # 保存到系统配置表
        success = save_ai_model_to_config(model_id, model_data)

        if success:
            return ApiResponse(
                code=0,
                message="创建AI模型配置成功",
                data=model_data,
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
@jwt_auth_required
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
    model_id: str = Path(..., description="配置ID"),
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

        # 从系统配置表读取
        all_models = get_ai_models_from_config()
        result = None
        for model in all_models:
            if str(model.get("id")) == str(model_id):
                result = model
                break

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
    model_id: str = Path(..., description="配置ID"),
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

        # 先获取现有配置
        all_models = get_ai_models_from_config()
        existing_model = None
        for model in all_models:
            if str(model.get("id")) == str(model_id):
                existing_model = model
                break
        
        if not existing_model:
            return ApiResponse(
                code=1,
                message="AI模型配置不存在",
                data=None,
            )
        
        # 更新数据
        updated_data = {
            "id": model_id,
            "provider": config.provider if config.provider else existing_model.get("provider"),
            "name": config.name if config.name else existing_model.get("name"),
            "api_key": config.api_key if config.api_key else existing_model.get("api_key"),
            "api_host": config.api_host if config.api_host else existing_model.get("api_host"),
            "models": config.models if config.models else existing_model.get("models"),
            "is_default": config.is_default if config.is_default is not None else existing_model.get("is_default"),
            "is_enabled": config.is_enabled if config.is_enabled is not None else existing_model.get("is_enabled"),
            "proxy_enabled": config.proxy_enabled if config.proxy_enabled is not None else existing_model.get("proxy_enabled"),
            "proxy_url": config.proxy_url if config.proxy_url else existing_model.get("proxy_url"),
            "proxy_username": config.proxy_username if config.proxy_username else existing_model.get("proxy_username"),
            "proxy_password": config.proxy_password if config.proxy_password else existing_model.get("proxy_password"),
            "created_at": existing_model.get("created_at"),
        }
        
        # 保存到系统配置表
        success = save_ai_model_to_config(model_id, updated_data)

        if success:
            return ApiResponse(
                code=0,
                message="更新AI模型配置成功",
                data=updated_data,
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
    model_id: str = Path(..., description="配置ID"),
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

        success = delete_ai_model_from_config(model_id)

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


@router.get("/default-provider/models", response_model=ApiResponse)
@jwt_auth_required_sync
def get_default_provider_models(
    request: Request,
):
    """获取默认提供商的模型列表

    从系统配置中读取默认提供商的配置，返回其 models 字段中 is_enabled 为 true 的模型列表。

    Args:
        request: FastAPI请求对象

    Returns:
        ApiResponse: 包含默认提供商模型列表的响应

    Responses:
        200: 成功获取模型列表
        401: 未授权访问
        404: 默认提供商不存在
        500: 获取失败
    """
    try:
        logger.info("获取默认提供商的模型列表")

        # 从系统配置表读取所有配置
        all_configs = SystemConfig.get_all_with_details()
        
        # 查找默认提供商ID
        default_provider_id = None
        providers_config = None
        
        for key, config in all_configs.items():
            if not isinstance(config, dict):
                continue
            if config.get("name") == AI_MODELS_CONFIG_NAME:
                # 查找 default_provider
                if key == "default_provider":
                    default_provider_id = config.get("value", "")
                # 查找 providers 配置
                elif key == "providers":
                    try:
                        providers_config = json.loads(config.get("value", "[]"))
                    except json.JSONDecodeError:
                        logger.warning(f"解析 providers 配置失败")
        
        if not default_provider_id:
            return ApiResponse(
                code=1,
                message="未设置默认提供商",
                data=None,
            )
        
        if not providers_config:
            return ApiResponse(
                code=1,
                message="未找到提供商配置",
                data=None,
            )
        
        # 查找默认提供商的配置
        default_provider = None
        for provider in providers_config:
            if isinstance(provider, dict) and provider.get("id") == default_provider_id:
                default_provider = provider
                break
        
        if not default_provider:
            return ApiResponse(
                code=1,
                message="默认提供商不存在",
                data=None,
            )
        
        # 获取 models 字段中 is_enabled 为 true 的模型
        models = default_provider.get("models", [])
        enabled_models = [
            {
                "id": model.get("id"),
                "name": model.get("name"),
            }
            for model in models
            if isinstance(model, dict) and model.get("is_enabled", False)
        ]
        
        logger.info(f"默认提供商 {default_provider_id} 有 {len(enabled_models)} 个启用的模型")

        return ApiResponse(
            code=0,
            message="获取默认提供商模型列表成功",
            data={
                "provider": {
                    "id": default_provider.get("id"),
                    "name": default_provider.get("name"),
                    "provider": default_provider.get("provider"),
                },
                "models": enabled_models,
                "total": len(enabled_models),
            },
        )
    except Exception as e:
        logger.error(f"获取默认提供商模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{model_id}/models", response_model=ApiResponse)
@jwt_auth_required
async def get_available_models(
    request: Request,
    model_id: str = Path(..., description="配置ID"),
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

        # 从系统配置表读取配置
        all_models = get_ai_models_from_config()
        config = None
        for model in all_models:
            if isinstance(model, dict) and str(model.get("id")) == str(model_id):
                config = model
                break
        
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
