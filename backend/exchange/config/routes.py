"""
交易所配置API路由

提供交易所配置的RESTful API端点。

路由前缀:
    - /api/exchange-configs: 交易所配置管理

标签: exchange-config

包含端点:
    - GET /api/exchange-configs: 获取配置列表
    - POST /api/exchange-configs: 创建配置
    - GET /api/exchange-configs/exchanges: 获取支持的交易所列表
    - GET /api/exchange-configs/{id}: 获取单个配置
    - PUT /api/exchange-configs/{id}: 更新配置
    - DELETE /api/exchange-configs/{id}: 删除配置
    - GET /api/exchange-configs/{id}/credentials: 获取API认证信息

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-02
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request
from loguru import logger

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required_sync

from .models import ExchangeConfigBusiness
from .schemas import (
    ExchangeConfigCreate,
    ExchangeConfigListResponse,
    ExchangeConfigResponse,
    ExchangeConfigUpdate,
)

# 创建API路由实例
router = APIRouter()

# 创建交易所配置API路由子路由
exchange_config_router = APIRouter(prefix="/api/exchange-configs", tags=["exchange-config"])


# 支持的交易所列表
SUPPORTED_EXCHANGES = [
    {"id": "binance", "name": "币安", "description": "全球最大的加密货币交易所"},
    {"id": "okx", "name": "OKX", "description": "全球领先的数字资产交易平台"},
]


@exchange_config_router.get("/", response_model=ApiResponse)
@jwt_auth_required_sync
def get_exchange_configs(
    request: Request,
    page: int = Query(1, ge=1, description="页码，从1开始"),
    limit: int = Query(10, ge=1, le=100, description="每页记录数"),
    exchange_id: Optional[str] = Query(None, description="按交易所ID筛选"),
    is_enabled: Optional[bool] = Query(None, description="按启用状态筛选"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序顺序，asc或desc"),
):
    """获取交易所配置列表

    Args:
        request: FastAPI请求对象
        page: 页码，从1开始
        limit: 每页记录数
        exchange_id: 按交易所ID筛选
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
        logger.info(f"获取交易所配置列表: page={page}, limit={limit}, exchange_id={exchange_id}")

        result = ExchangeConfigBusiness.list(
            page=page,
            limit=limit,
            exchange_id=exchange_id,
            is_enabled=is_enabled,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return ApiResponse(
            code=0,
            message="获取交易所配置列表成功",
            data=result,
        )
    except Exception as e:
        logger.error(f"获取交易所配置列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_config_router.post("/", response_model=ApiResponse)
@jwt_auth_required_sync
def create_exchange_config(request: Request, config: ExchangeConfigCreate):
    """创建交易所配置

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
        logger.info(f"创建交易所配置: exchange_id={config.exchange_id}, name={config.name}")

        result = ExchangeConfigBusiness.create(
            exchange_id=config.exchange_id,
            name=config.name,
            trading_mode=config.trading_mode,
            quote_currency=config.quote_currency,
            commission_rate=config.commission_rate,
            api_key=config.api_key,
            api_secret=config.api_secret,
            proxy_enabled=config.proxy_enabled,
            proxy_url=config.proxy_url,
            proxy_username=config.proxy_username,
            proxy_password=config.proxy_password,
            is_default=config.is_default,
            is_enabled=config.is_enabled,
        )

        if result:
            return ApiResponse(
                code=0,
                message="创建交易所配置成功",
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message="创建交易所配置失败",
                data=None,
            )
    except Exception as e:
        logger.error(f"创建交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_config_router.get("/exchanges", response_model=ApiResponse)
@jwt_auth_required_sync
def get_supported_exchanges(request: Request):
    """获取支持的交易所列表

    Args:
        request: FastAPI请求对象

    Returns:
        ApiResponse: 包含支持的交易所列表的响应

    Responses:
        200: 成功获取交易所列表
        401: 未授权访问
    """
    try:
        logger.info("获取支持的交易所列表")

        return ApiResponse(
            code=0,
            message="获取支持的交易所列表成功",
            data={"exchanges": SUPPORTED_EXCHANGES},
        )
    except Exception as e:
        logger.error(f"获取支持的交易所列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_config_router.get("/{config_id}", response_model=ApiResponse)
@jwt_auth_required_sync
def get_exchange_config(
    request: Request,
    config_id: int = Path(..., ge=1, description="配置ID"),
):
    """获取单个交易所配置

    Args:
        request: FastAPI请求对象
        config_id: 配置ID

    Returns:
        ApiResponse: 包含配置信息的响应

    Responses:
        200: 成功获取配置
        401: 未授权访问
        404: 配置不存在
        500: 获取配置失败
    """
    try:
        logger.info(f"获取交易所配置: id={config_id}")

        result = ExchangeConfigBusiness.get_by_id(config_id)

        if result:
            return ApiResponse(
                code=0,
                message="获取交易所配置成功",
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message="交易所配置不存在",
                data=None,
            )
    except Exception as e:
        logger.error(f"获取交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_config_router.put("/{config_id}", response_model=ApiResponse)
@jwt_auth_required_sync
def update_exchange_config(
    request: Request,
    config: ExchangeConfigUpdate,
    config_id: int = Path(..., ge=1, description="配置ID"),
):
    """更新交易所配置

    Args:
        request: FastAPI请求对象
        config: 配置更新请求体
        config_id: 配置ID

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
        logger.info(f"更新交易所配置: id={config_id}")

        result = ExchangeConfigBusiness.update(
            config_id=config_id,
            exchange_id=config.exchange_id,
            name=config.name,
            trading_mode=config.trading_mode,
            quote_currency=config.quote_currency,
            commission_rate=config.commission_rate,
            api_key=config.api_key,
            api_secret=config.api_secret,
            proxy_enabled=config.proxy_enabled,
            proxy_url=config.proxy_url,
            proxy_username=config.proxy_username,
            proxy_password=config.proxy_password,
            is_default=config.is_default,
            is_enabled=config.is_enabled,
        )

        if result:
            return ApiResponse(
                code=0,
                message="更新交易所配置成功",
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message="交易所配置不存在或更新失败",
                data=None,
            )
    except Exception as e:
        logger.error(f"更新交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_config_router.delete("/{config_id}", response_model=ApiResponse)
@jwt_auth_required_sync
def delete_exchange_config(
    request: Request,
    config_id: int = Path(..., ge=1, description="配置ID"),
):
    """删除交易所配置

    Args:
        request: FastAPI请求对象
        config_id: 配置ID

    Returns:
        ApiResponse: 包含删除结果的响应

    Responses:
        200: 删除成功
        401: 未授权访问
        404: 配置不存在
        500: 删除失败
    """
    try:
        logger.info(f"删除交易所配置: id={config_id}")

        success = ExchangeConfigBusiness.delete(config_id)

        if success:
            return ApiResponse(
                code=0,
                message="删除交易所配置成功",
                data={"id": config_id},
            )
        else:
            return ApiResponse(
                code=1,
                message="交易所配置不存在或删除失败",
                data=None,
            )
    except Exception as e:
        logger.error(f"删除交易所配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@exchange_config_router.get("/{config_id}/credentials", response_model=ApiResponse)
@jwt_auth_required_sync
def get_exchange_credentials(
    request: Request,
    config_id: int = Path(..., ge=1, description="配置ID"),
):
    """获取交易所API认证信息

    获取指定交易所配置的原始API密钥信息（需要授权）。

    Args:
        request: FastAPI请求对象
        config_id: 配置ID

    Returns:
        ApiResponse: 包含API认证信息的响应

    Responses:
        200: 成功获取认证信息
        401: 未授权访问
        404: 配置不存在
        500: 获取失败
    """
    try:
        logger.info(f"获取交易所API认证信息: id={config_id}")

        result = ExchangeConfigBusiness.get_api_credentials(config_id)

        if result:
            return ApiResponse(
                code=0,
                message="获取API认证信息成功",
                data=result,
            )
        else:
            return ApiResponse(
                code=1,
                message="交易所配置不存在",
                data=None,
            )
    except Exception as e:
        logger.error(f"获取API认证信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册子路由
router.include_router(exchange_config_router)
