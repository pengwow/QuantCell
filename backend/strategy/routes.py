# 策略API路由
# 实现策略相关的API接口

from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Path
from loguru import logger

from .service import StrategyService
from .schemas import (
    StrategyListResponse,
    StrategyUploadRequest,
    StrategyUploadResponse,
    StrategyExecutionRequest,
    StrategyExecutionResponse,
    StrategyParseRequest,
    StrategyParseResponse,
    StrategyDetailRequest,
    StrategyInfo
)
from common.schemas import ApiResponse

# 创建策略API路由实例
router_strategy = APIRouter(
    prefix="/api/strategy",
    tags=["strategy"],
    responses={
        200: {"description": "成功响应"},
        500: {"description": "内部服务器错误"},
    },
)

# 创建策略服务实例
strategy_service = StrategyService()


@router_strategy.get(
    "/list",
    response_model=StrategyListResponse,
    summary="获取策略列表",
    description="获取所有可用策略的列表，包含策略名称、描述、参数等详细信息，支持从实体文件、数据库表或两者同时获取",
    responses={
        200: {"description": "获取策略列表成功"},
        400: {"description": "请求参数错误"},
        500: {"description": "获取策略列表失败"},
    },
)
def get_strategy_list(source: Optional[str] = None):
    """
    获取所有可用策略的列表

    Args:
        source: 策略来源，可选值："files"表示从实体文件获取，"db"表示从数据库表获取，空值表示两者同时获取

    Returns:
        StrategyListResponse: 策略列表响应，包含所有可用策略的详细信息，每个策略包含source字段区分来源
    """
    try:
        # 验证source参数
        if source is not None and source not in ["files", "db"]:
            logger.error(f"获取策略列表请求，无效的来源参数: {source}")
            raise HTTPException(status_code=400, detail="无效的source参数，只允许files、db或空值")
        
        logger.info(f"获取策略列表请求，来源: {source}")

        # 获取策略列表
        strategies = strategy_service.get_strategy_list(source)

        logger.info(f"成功获取策略列表，共 {len(strategies)} 个策略")

        return StrategyListResponse(
            code=0, message="获取策略列表成功", data={"strategies": strategies}
        )
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_strategy.post(
    "/detail",
    response_model=ApiResponse,
    summary="获取策略详情",
    description="获取单个策略的详细信息，包含策略代码、参数定义等完整信息，支持通过文件名或文件内容获取",
    responses={
        200: {"description": "获取策略详情成功"},
        404: {"description": "策略不存在"},
        500: {"description": "获取策略详情失败"},
    }
)
def get_strategy_detail(request: StrategyDetailRequest):
    """
    获取单个策略的详细信息

    Args:
        request: 策略详情请求，包含策略名称和可选的文件内容

    Returns:
        dict: 策略详情响应，包含策略的完整信息
    """
    try:
        logger.info(f"获取策略详情请求，策略名称: {request.strategy_name}")

        # 获取策略详情
        strategy_info = strategy_service.get_strategy_detail(
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


@router_strategy.post(
    "/upload",
    response_model=StrategyUploadResponse,
    summary="上传策略文件",
    description="上传新的策略文件到系统，支持自定义策略版本和描述",
    responses={
        200: {"description": "策略文件上传成功"},
        500: {"description": "策略文件上传失败"},
    },
)
def upload_strategy(request: StrategyUploadRequest):
    """
    上传新的策略文件到系统

    Args:
        request: 策略文件上传请求，包含策略名称、文件内容、可选的版本和描述

    Returns:
        StrategyUploadResponse: 策略文件上传响应
    """
    try:
        logger.info(f"上传策略文件请求，策略名称: {request.strategy_name}")

        # 上传策略文件，传递所有参数，包括id
        success = strategy_service.upload_strategy_file(
            request.strategy_name,
            request.file_content,
            request.version,
            request.description,
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
            return StrategyUploadResponse(code=1, message="策略文件上传失败")
    except Exception as e:
        logger.error(f"上传策略文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_strategy.post(
    "/{strategy_name}/execute",
    response_model=StrategyExecutionResponse,
    summary="执行策略",
    description="执行指定策略，支持回测和实盘两种模式",
    responses={
        200: {"description": "策略执行成功"},
        404: {"description": "策略不存在"},
        500: {"description": "策略执行失败"},
    },
)
def execute_strategy(
    request: StrategyExecutionRequest,
    strategy_name: str = Path(..., description="策略名称", example="sma_cross"),
):
    """
    执行指定策略

    Args:
        request: 策略执行请求，包含执行参数和配置
        strategy_name: 策略名称

    Returns:
        StrategyExecutionResponse: 策略执行响应，包含执行ID和状态
    """
    try:
        logger.info(
            f"执行策略请求，策略名称: {strategy_name}, 执行模式: {request.mode}"
        )

        # 验证策略是否存在
        strategy_cls = strategy_service.load_strategy(strategy_name)
        if not strategy_cls:
            logger.error(f"策略不存在: {strategy_name}")
            raise HTTPException(status_code=404, detail="策略不存在")

        # TODO: 实现策略执行逻辑
        # 1. 创建策略实例
        # 2. 设置策略参数
        # 3. 根据执行模式选择回测或实盘
        # 4. 执行策略
        # 5. 返回执行结果

        # 目前返回模拟执行结果
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


@router_strategy.post(
    "/parse",
    response_model=StrategyParseResponse,
    summary="解析策略脚本",
    description="解析策略脚本，提取策略描述和参数信息",
    responses={
        200: {"description": "策略脚本解析成功"},
        500: {"description": "策略脚本解析失败"},
    },
)
def parse_strategy(request: StrategyParseRequest):
    """
    解析策略脚本，提取策略描述和参数信息

    Args:
        request: 策略脚本解析请求，包含策略名称和文件内容

    Returns:
        StrategyParseResponse: 策略脚本解析响应，包含策略描述和参数信息
    """
    try:
        logger.info(f"解析策略脚本请求，策略名称: {request.strategy_name}")

        # 解析策略脚本
        strategy_info = strategy_service.get_strategy_detail(
            request.strategy_name, request.file_content
        )

        if not strategy_info:
            logger.error(f"解析策略脚本失败: {request.strategy_name}")
            raise HTTPException(status_code=500, detail="解析策略脚本失败")

        logger.info(f"策略脚本解析成功: {request.strategy_name}")

        return StrategyParseResponse(
            code=0, message="策略脚本解析成功", data={"strategy": strategy_info}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解析策略脚本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_strategy.delete(
    "/{strategy_name}",
    summary="删除策略",
    description="删除策略，包括策略文件和数据库记录",
    responses={
        200: {"description": "删除策略成功"},
        404: {"description": "策略不存在"},
        500: {"description": "删除策略失败"},
    },
)
def delete_strategy(strategy_name: str = Path(..., description="策略名称", example="sma_cross")):
    """
    删除策略，包括策略文件和数据库记录

    Args:
        strategy_name: 策略名称

    Returns:
        Dict[str, Any]: 删除结果响应
    """
    try:
        logger.info(f"删除策略请求，策略名称: {strategy_name}")

        # 调用策略服务删除策略
        success = strategy_service.delete_strategy(strategy_name)

        if success:
            logger.info(f"删除策略成功，策略名称: {strategy_name}")
            return {
                "code": 0,
                "message": "删除策略成功",
                "data": {"strategy_name": strategy_name}
            }
        else:
            logger.error(f"删除策略失败，策略名称: {strategy_name}")
            raise HTTPException(status_code=500, detail="删除策略失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
