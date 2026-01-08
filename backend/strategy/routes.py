# 策略API路由
# 实现策略相关的API接口

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path
from loguru import logger

from .service import StrategyService
from .schemas import (
    StrategyListResponse,
    StrategyUploadRequest,
    StrategyUploadResponse,
    StrategyDetailResponse,
    StrategyExecutionRequest,
    StrategyExecutionResponse
)

# 创建策略API路由实例
router_strategy = APIRouter(
    prefix="/api/strategy", 
    tags=["strategy"],
    responses={
        200: {"description": "成功响应"},
        500: {"description": "内部服务器错误"}
    }
)

# 创建策略服务实例
strategy_service = StrategyService()


@router_strategy.get(
    "/list", 
    response_model=StrategyListResponse,
    summary="获取策略列表",
    description="获取所有可用策略的列表，包含策略名称、描述、参数等详细信息",
    responses={
        200: {"description": "获取策略列表成功"},
        500: {"description": "获取策略列表失败"}
    }
)
def get_strategy_list():
    """
    获取所有可用策略的列表
    
    Returns:
        StrategyListResponse: 策略列表响应，包含所有可用策略的详细信息
    """
    try:
        logger.info("获取策略列表请求")
        
        # 获取策略列表
        strategies = strategy_service.get_strategy_list()
        
        logger.info(f"成功获取策略列表，共 {len(strategies)} 个策略")
        
        return StrategyListResponse(
            code=0,
            message="获取策略列表成功",
            data={"strategies": strategies}
        )
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_strategy.get(
    "/{strategy_name}", 
    response_model=StrategyDetailResponse,
    summary="获取策略详情",
    description="获取单个策略的详细信息，包含策略代码、参数定义等完整信息",
    responses={
        200: {"description": "获取策略详情成功"},
        404: {"description": "策略不存在"},
        500: {"description": "获取策略详情失败"}
    }
)
def get_strategy_detail(
    strategy_name: str = Path(..., description="策略名称", example="sma_cross")
):
    """
    获取单个策略的详细信息
    
    Args:
        strategy_name: 策略名称
        
    Returns:
        StrategyDetailResponse: 策略详情响应，包含策略的完整信息
    """
    try:
        logger.info(f"获取策略详情请求，策略名称: {strategy_name}")
        
        # 获取策略详情
        strategy_info = strategy_service.get_strategy_detail(strategy_name)
        
        if not strategy_info:
            logger.error(f"策略不存在: {strategy_name}")
            raise HTTPException(status_code=404, detail="策略不存在")
        
        logger.info(f"成功获取策略详情: {strategy_name}")
        
        return StrategyDetailResponse(
            code=0,
            message="获取策略详情成功",
            data={"strategy": strategy_info}
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
    description="上传新的策略文件到系统",
    responses={
        200: {"description": "策略文件上传成功"},
        500: {"description": "策略文件上传失败"}
    }
)
def upload_strategy(request: StrategyUploadRequest):
    """
    上传新的策略文件到系统
    
    Args:
        request: 策略文件上传请求，包含策略名称和文件内容
        
    Returns:
        StrategyUploadResponse: 策略文件上传响应
    """
    try:
        logger.info(f"上传策略文件请求，策略名称: {request.strategy_name}")
        
        # 上传策略文件
        success = strategy_service.upload_strategy_file(
            request.strategy_name,
            request.file_content
        )
        
        if success:
            logger.info(f"策略文件上传成功，策略名称: {request.strategy_name}")
            return StrategyUploadResponse(
                code=0,
                message="策略文件上传成功",
                data={"strategy_name": request.strategy_name}
            )
        else:
            logger.error(f"策略文件上传失败，策略名称: {request.strategy_name}")
            return StrategyUploadResponse(
                code=1,
                message="策略文件上传失败"
            )
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
        500: {"description": "策略执行失败"}
    }
)
def execute_strategy(
    request: StrategyExecutionRequest,
    strategy_name: str = Path(..., description="策略名称", example="sma_cross")
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
        logger.info(f"执行策略请求，策略名称: {strategy_name}, 执行模式: {request.mode}")
        
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
                "result_url": f"/api/strategy/execution/{execution_id}/result"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
