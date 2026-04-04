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
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from common.schemas import ApiResponse
from utils.auth import jwt_auth_required, jwt_auth_required_sync

# 导入系统配置模型
from settings.models import SystemConfigBusiness as SystemConfig

from .config_utils import get_default_provider_and_models
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


def get_ai_models_from_config() -> List[Dict[str, Any]]:
    """从系统配置表读取AI模型配置
    
    使用新的 ai_model.{provider_id}.{field} 格式读取配置
    
    Returns:
        List[Dict[str, Any]]: AI模型提供商配置列表
    """
    try:
        from .config_utils import get_all_providers
        
        # 使用新的配置解析方法
        providers = get_all_providers()
        
        logger.info(f"获取到 {len(providers)} 个AI模型提供商配置")
        for provider in providers:
            logger.info(f"提供商: id={provider.get('id')}, name={provider.get('name')}, enabled={provider.get('is_enabled')}")
        
        return providers
    except Exception as e:
        logger.error(f"从系统配置读取AI模型失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def save_ai_model_to_config(model_id: str, model_data: Dict[str, Any]) -> bool:
    """保存AI模型配置到系统配置表
    
    使用新的 ai_model.{provider_id}.{field} 格式存储
    
    Args:
        model_id: 模型配置ID
        model_data: 模型配置数据
        
    Returns:
        bool: 是否保存成功
    """
    try:
        # 将模型数据分解为多个配置项
        fields_to_save = [
            "name", "provider", "api_key", "api_host", 
            "models", "is_default", "is_enabled",
            "proxy_enabled", "proxy_url", "proxy_username", "proxy_password"
        ]
        
        for field in fields_to_save:
            value = model_data.get(field)
            if value is not None:
                # 特殊处理复杂字段
                if field == "models" and isinstance(value, list):
                    value = json.dumps(value, ensure_ascii=False)
                elif field in ["is_default", "proxy_enabled"]:
                    # 布尔字段
                    value = "true" if value else "false"
                elif field == "is_enabled":
                    # is_enabled 直接存储模型ID字符串（或空字符串）
                    value = str(value) if value else ""
                
                key = f"{AI_MODELS_CONFIG_NAME}.{model_id}.{field}"
                SystemConfig.set(
                    key=key,
                    value=str(value),
                    description=f"{model_data.get('name', 'AI模型')}的{field}配置",
                    name=AI_MODELS_CONFIG_NAME
                )
        
        return True
    except Exception as e:
        logger.error(f"保存AI模型配置失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def delete_ai_model_from_config(model_id: str) -> bool:
    """从系统配置表删除AI模型配置
    
    删除该提供商的所有配置项
    
    Args:
        model_id: 模型配置ID
        
    Returns:
        bool: 是否删除成功
    """
    try:
        from settings.models import SystemConfigBusiness as SystemConfig
        
        # 获取所有配置
        all_configs = SystemConfig.get_all_with_details()
        
        # 删除该提供商的所有配置项
        prefix = f"{AI_MODELS_CONFIG_NAME}.{model_id}."
        for key in list(all_configs.keys()):
            if key.startswith(prefix):
                # 使用set设置空值来删除
                SystemConfig.set(
                    key=key,
                    value="",
                    description="",
                    name=""
                )
        
        return True
    except Exception as e:
        logger.error(f"删除AI模型配置失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
        all_providers = get_ai_models_from_config()
        
        # 筛选
        filtered_providers = all_providers
        if provider:
            filtered_providers = [p for p in filtered_providers if p.get("id") == provider]

        if is_default is not None:
            if is_default:
                # 只返回默认提供商
                filtered_providers = [p for p in filtered_providers if p.get("is_default", False)]
            else:
                # 返回非默认提供商
                filtered_providers = [p for p in filtered_providers if not p.get("is_default", False)]

        # 排序
        reverse = sort_order.lower() == "desc"
        filtered_providers.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)
        
        # 分页
        total = len(filtered_providers)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_providers = filtered_providers[start_idx:end_idx]

        return ApiResponse(
            code=0,
            message="获取AI模型配置列表成功",
            data={
                "items": paginated_providers,
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
    """获取默认提供商的模型

    从系统配置中读取默认提供商的配置，返回其第一个启用的模型。
    使用 get_default_provider_and_models 公共方法获取配置。

    Args:
        request: FastAPI请求对象

    Returns:
        ApiResponse: 包含默认提供商和默认模型的响应

    Responses:
        200: 成功获取模型
        401: 未授权访问
        404: 默认提供商不存在
        500: 获取失败
    """
    try:
        logger.info("获取默认提供商的模型")

        # 使用公共方法获取默认提供商和模型
        result = get_default_provider_and_models()

        if not result:
            return ApiResponse(
                code=1,
                message="未配置默认AI模型或提供商",
                data=None,
            )

        provider = result["provider"]
        enabled_models = result["enabled_models"]

        # 获取第一个启用的模型作为默认模型
        default_model = enabled_models[0] if enabled_models else None

        logger.info(f"默认提供商 {provider['id']} 的默认模型: {default_model['name'] if default_model else '无'}")

        return ApiResponse(
            code=0,
            message="获取默认提供商模型成功",
            data={
                "provider": {
                    "id": provider.get("id"),
                    "name": provider.get("name"),
                    "provider": provider.get("provider"),
                },
                "model": default_model,
            },
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"获取默认提供商模型失败: {error_msg}")
        
        # 提供更友好的错误信息
        if "no such table" in error_msg.lower():
            friendly_msg = "数据库表不存在，请先运行初始化脚本: cd backend && uv run python scripts/init_ai_model.py"
        elif "operationalerror" in error_msg.lower():
            friendly_msg = "数据库操作错误，请检查数据库配置或运行初始化脚本"
        else:
            friendly_msg = f"获取 AI 模型配置失败: {error_msg}"
        
        return ApiResponse(
            code=500,
            message=friendly_msg,
            data={"error_detail": error_msg},
        )


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
