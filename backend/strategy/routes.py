"""
策略模块API路由

提供策略相关的RESTful API端点。

路由前缀: /api/strategy
标签: strategy

包含端点:
    - GET /list: 获取策略列表
    - POST /detail: 获取策略详情
    - POST /upload: 上传策略文件
    - POST /parse: 解析策略脚本
    - POST /{strategy_name}/execute: 执行策略
    - DELETE /{strategy_name}: 删除策略

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Request
from loguru import logger

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required_sync

from .schemas import (
    StrategyListResponse,
    StrategyUploadRequest,
    StrategyUploadResponse,
    StrategyExecutionRequest,
    StrategyExecutionResponse,
    StrategyParseRequest,
    StrategyParseResponse,
    StrategyDetailRequest,
)
from .service import StrategyService

# 策略服务实例（延迟初始化）
_strategy_service: Optional[StrategyService] = None


def get_strategy_service() -> StrategyService:
    """获取策略服务实例（延迟初始化）"""
    global _strategy_service
    if _strategy_service is None:
        _strategy_service = StrategyService()
    return _strategy_service


# 创建API路由实例
router = APIRouter(
    prefix="/api/strategy",
    tags=["strategy"],
    responses={
        200: {"description": "成功响应"},
        400: {"description": "请求参数错误"},
        404: {"description": "资源不存在"},
        500: {"description": "内部服务器错误"},
    },
)


@router.get(
    "/list",
    response_model=StrategyListResponse,
    summary="获取策略列表",
    description="获取所有可用策略的列表，支持从实体文件、数据库表或两者同时获取",
)
def get_strategy_list(source: Optional[str] = None) -> StrategyListResponse:
    """
    获取所有可用策略的列表

    Args:
        source: 策略来源，可选值："files"表示从实体文件获取，"db"表示从数据库表获取，空值表示两者同时获取

    Returns:
        StrategyListResponse: 策略列表响应
    """
    # 验证source参数
    if source is not None and source not in ["files", "db"]:
        logger.error(f"获取策略列表请求，无效的来源参数: {source}")
        raise HTTPException(status_code=400, detail="无效的source参数，只允许files、db或空值")

    try:
        logger.info(f"获取策略列表请求，来源: {source}")

        # 获取策略列表
        strategies = get_strategy_service().get_strategy_list(source)

        logger.info(f"成功获取策略列表，共 {len(strategies)} 个策略")

        return StrategyListResponse(
            code=0, message="获取策略列表成功", data={"strategies": strategies}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/detail",
    response_model=ApiResponse,
    summary="获取策略详情",
    description="获取单个策略的详细信息，包含策略代码、参数定义等完整信息",
)
def get_strategy_detail(request: StrategyDetailRequest) -> ApiResponse:
    """
    获取单个策略的详细信息

    Args:
        request: 策略详情请求，包含策略名称和可选的文件内容

    Returns:
        ApiResponse: 策略详情响应
    """
    try:
        logger.info(f"获取策略详情请求，策略名称: {request.strategy_name}")

        # 获取策略详情
        strategy_info = get_strategy_service().get_strategy_detail(
            request.strategy_name,
            request.file_content
        )

        if not strategy_info:
            logger.error(f"策略不存在: {request.strategy_name}")
            raise HTTPException(status_code=404, detail="策略不存在")

        logger.info(f"成功获取策略详情: {request.strategy_name}")

        return ApiResponse(
            code=0,
            message="获取策略详情成功",
            data=strategy_info
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取策略详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/upload",
    response_model=StrategyUploadResponse,
    summary="上传策略文件",
    description="上传新的策略文件到系统，支持自定义策略版本和描述",
)
def upload_strategy(request: StrategyUploadRequest) -> StrategyUploadResponse:
    """
    上传新的策略文件到系统

    Args:
        request: 策略文件上传请求

    Returns:
        StrategyUploadResponse: 策略文件上传响应
    """
    try:
        logger.info(f"上传策略文件请求，策略名称: {request.strategy_name}")

        # 上传策略文件
        success = get_strategy_service().upload_strategy_file(
            request.strategy_name,
            request.file_content,
            request.version,
            request.description,
            request.tags,
            request.id
        )

        if success:
            logger.info(f"策略文件上传成功，策略名称: {request.strategy_name}")
            return StrategyUploadResponse(
                code=0,
                message="策略文件上传成功",
                data={"strategy_name": request.strategy_name},
            )
        else:
            logger.error(f"策略文件上传失败，策略名称: {request.strategy_name}")
            return StrategyUploadResponse(code=1, message="策略文件上传失败", data={})
    except Exception as e:
        logger.error(f"上传策略文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/parse",
    response_model=StrategyParseResponse,
    summary="解析策略脚本",
    description="解析策略脚本，提取策略描述和参数信息",
)
def parse_strategy(request: StrategyParseRequest) -> StrategyParseResponse:
    """
    解析策略脚本，提取策略描述和参数信息

    Args:
        request: 策略脚本解析请求

    Returns:
        StrategyParseResponse: 策略脚本解析响应
    """
    # 验证文件内容是否为空
    if request.file_content is None or request.file_content.strip() == "":
        logger.error("解析策略脚本失败: 文件内容为空")
        raise HTTPException(status_code=400, detail="文件内容不能为空")

    try:
        logger.info(f"解析策略脚本请求，策略名称: {request.strategy_name}")

        # 解析策略脚本
        strategy_info = get_strategy_service().get_strategy_detail(
            request.strategy_name, request.file_content
        )

        if not strategy_info:
            logger.error(f"解析策略脚本失败: {request.strategy_name}")
            raise HTTPException(status_code=400, detail="解析策略脚本失败，无法识别策略类")

        logger.info(f"策略脚本解析成功: {request.strategy_name}")

        return StrategyParseResponse(
            code=0, message="策略脚本解析成功", data={"strategy": strategy_info}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解析策略脚本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{strategy_name}/execute",
    response_model=StrategyExecutionResponse,
    summary="执行策略",
    description="执行指定策略，支持回测和实盘两种模式",
)
def execute_strategy(
    request: StrategyExecutionRequest,
    strategy_name: str = Path(..., description="策略名称"),
) -> StrategyExecutionResponse:
    """
    执行指定策略

    Args:
        request: 策略执行请求
        strategy_name: 策略名称

    Returns:
        StrategyExecutionResponse: 策略执行响应
    """
    try:
        logger.info(
            f"执行策略请求，策略名称: {strategy_name}, 执行模式: {request.mode}"
        )

        # 验证策略是否存在
        strategy_cls = get_strategy_service().load_strategy(strategy_name)
        if not strategy_cls:
            logger.error(f"策略不存在: {strategy_name}")
            raise HTTPException(status_code=404, detail="策略不存在")

        # TODO: 实现策略执行逻辑
        execution_id = f"uuid-{strategy_name}-{hash(str(request))}"

        logger.info(f"策略执行成功，执行ID: {execution_id}")

        return StrategyExecutionResponse(
            code=0,
            message="策略执行成功",
            data={
                "execution_id": execution_id,
                "status": "running",
                "result_url": f"/api/strategy/execution/{execution_id}/result",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/{strategy_name}",
    response_model=ApiResponse,
    summary="删除策略",
    description="删除策略，包括策略文件和数据库记录",
)
@jwt_auth_required_sync
def delete_strategy(
    request: Request,
    strategy_name: str = Path(..., description="策略名称")
) -> ApiResponse:
    """
    删除策略，包括策略文件和数据库记录

    Args:
        strategy_name: 策略名称

    Returns:
        ApiResponse: 删除结果响应
    """
    try:
        logger.info(f"删除策略请求，策略名称: {strategy_name}")

        # 调用策略服务删除策略
        success = get_strategy_service().delete_strategy(strategy_name)

        if success:
            logger.info(f"删除策略成功，策略名称: {strategy_name}")
            return ApiResponse(
                code=0,
                message="删除策略成功",
                data={"strategy_name": strategy_name}
            )
        else:
            logger.error(f"删除策略失败，策略名称: {strategy_name}")
            raise HTTPException(status_code=500, detail="删除策略失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
