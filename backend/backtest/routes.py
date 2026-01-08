# 回测服务API路由

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from .schemas import (ApiResponse, BacktestAnalyzeRequest,
                      BacktestDeleteRequest, BacktestListRequest,
                      BacktestRunRequest, StrategyConfigRequest,
                      StrategyUploadRequest, BacktestReplayRequest)
from .service import BacktestService

# 创建API路由实例
router = APIRouter()

# 创建回测服务实例
backtest_service = BacktestService()

# 创建回测API路由子路由
router_backtest = APIRouter(
    prefix="/api/backtest", 
    tags=["backtest"],
    responses={
        200: {"description": "成功响应", "model": ApiResponse},
        500: {"description": "内部服务器错误"}
    }
)

@router_backtest.get(
    "/list", 
    response_model=ApiResponse,
    summary="获取回测列表",
    description="获取所有回测任务的列表，支持分页查询",
    responses={
        200: {"description": "获取回测列表成功"},
        500: {"description": "获取回测列表失败"}
    }
)
def get_backtest_list(request: BacktestListRequest = None):
    """
    获取所有回测结果列表
    
    Args:
        request: 回测列表请求参数，包含分页信息，可选
        
    Returns:
        ApiResponse: API响应，包含回测结果列表
    """
    try:
        logger.info("获取回测结果列表请求")
        
        # 获取回测结果列表
        backtests = backtest_service.list_backtest_results()
        
        logger.info(f"成功获取回测结果列表，共 {len(backtests)} 个回测结果")
        
        return ApiResponse(
            code=0,
            message="获取回测结果列表成功",
            data={"backtests": backtests}
        )
    except Exception as e:
        logger.error(f"获取回测结果列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.get("/strategies", response_model=ApiResponse)
def get_strategy_list():
    """
    获取所有支持的策略类型列表
    
    Returns:
        ApiResponse: API响应，包含策略类型列表
    """
    try:
        logger.info("获取策略类型列表请求")
        
        # 直接返回空列表，保持原有接口，但实际不再使用
        # 建议前端使用新的 /api/strategy/list 接口
        strategies = []
        
        logger.info("成功获取策略类型列表")
        
        return ApiResponse(
            code=0,
            message="获取策略类型列表成功",
            data={"strategies": strategies}
        )
    except Exception as e:
        logger.error(f"获取策略类型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post(
    "/run", 
    response_model=ApiResponse,
    summary="执行回测",
    description="根据策略配置和回测配置执行回测，返回回测结果",
    responses={
        200: {
            "description": "回测执行成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 0,
                        "message": "回测执行成功",
                        "data": {
                            "task_id": "bt_1234567890",
                            "status": "completed",
                            "message": "回测完成"
                        }
                    }
                }
            }
        },
        500: {"description": "回测执行失败"}
    }
)
def run_backtest(request: BacktestRunRequest):
    """
    执行回测
    
    Args:
        request: 回测执行请求参数，包含策略配置和回测配置
        
    Returns:
        ApiResponse: API响应，包含回测结果
    """
    try:
        logger.info(f"执行回测请求，参数: {request.model_dump()}")
        
        # 执行回测
        result = backtest_service.run_backtest(
            strategy_config=request.strategy_config.model_dump(),
            backtest_config=request.backtest_config.model_dump()
        )
        
        logger.info(f"回测执行完成，结果: {result}")
        
        return ApiResponse(
            code=0,
            message="回测执行成功",
            data=result
        )
    except Exception as e:
        logger.error(f"回测执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post("/analyze", response_model=ApiResponse)
def analyze_backtest(request: BacktestAnalyzeRequest):
    """
    分析回测结果
    
    Args:
        request: 回测分析请求参数，包含回测ID
        
    Returns:
        ApiResponse: API响应，包含回测分析结果
    """
    try:
        logger.info(f"分析回测结果请求，回测ID: {request.backtest_id}")
        
        # 分析回测结果
        result = backtest_service.analyze_backtest(request.backtest_id)
        
        logger.info(f"回测结果分析完成，结果: {result}")
        
        return ApiResponse(
            code=0,
            message="回测结果分析成功",
            data=result
        )
    except Exception as e:
        logger.error(f"回测结果分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.delete("/delete/{backtest_id}", response_model=ApiResponse)
def delete_backtest(backtest_id: str):
    """
    删除回测结果
    
    Args:
        backtest_id: 回测ID
        
    Returns:
        ApiResponse: API响应，包含回测删除结果
    """
    try:
        logger.info(f"删除回测结果请求，回测ID: {backtest_id}")
        
        # 删除回测结果
        result = backtest_service.delete_backtest_result(backtest_id)
        
        if result:
            logger.info(f"回测结果删除成功，回测ID: {backtest_id}")
            return ApiResponse(
                code=0,
                message="回测结果删除成功",
                data={"backtest_id": backtest_id, "result": result}
            )
        else:
            logger.warning(f"回测结果删除失败，回测ID: {backtest_id}")
            return ApiResponse(
                code=1,
                message="回测结果删除失败",
                data={"backtest_id": backtest_id, "result": result}
            )
    except Exception as e:
        logger.error(f"回测结果删除失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post("/strategy/config", response_model=ApiResponse)
def create_strategy_config(request: StrategyConfigRequest):
    """
    创建策略配置
    
    Args:
        request: 策略配置请求参数，包含策略名称和参数
        
    Returns:
        ApiResponse: API响应，包含策略配置
    """
    try:
        logger.info(f"创建策略配置请求，策略名称: {request.strategy_name}")
        
        # 创建策略配置
        strategy_config = {
            "strategy_name": request.strategy_name,
            "params": request.params
        }
        
        logger.info(f"策略配置创建成功，策略名称: {request.strategy_name}")
        return ApiResponse(
            code=0,
            message="策略配置创建成功",
            data={"strategy_config": strategy_config}
        )
    except Exception as e:
        logger.error(f"策略配置创建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post("/strategy", response_model=ApiResponse)
def upload_strategy(request: StrategyUploadRequest):
    """
    上传策略文件
    
    Args:
        request: 策略上传请求参数，包含策略名称和文件内容
        
    Returns:
        ApiResponse: API响应，包含策略上传结果
    """
    try:
        logger.info(f"上传策略文件请求，策略名称: {request.strategy_name}")
        
        # 上传策略文件
        result = backtest_service.upload_strategy_file(
            strategy_name=request.strategy_name,
            file_content=request.file_content
        )
        
        if result:
            logger.info(f"策略文件上传成功，策略名称: {request.strategy_name}")
            return ApiResponse(
                code=0,
                message="策略文件上传成功",
                data={"strategy_name": request.strategy_name}
            )
        else:
            logger.error(f"策略文件上传失败，策略名称: {request.strategy_name}")
            return ApiResponse(
                code=1,
                message="策略文件上传失败",
                data={}
            )
    except Exception as e:
        logger.error(f"策略文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.get("/{backtest_id}", response_model=ApiResponse)
def get_backtest_detail(backtest_id: str):
    """
    获取回测结果详情
    
    Args:
        backtest_id: 回测ID
        
    Returns:
        ApiResponse: API响应，包含回测结果详情
    """
    try:
        logger.info(f"获取回测结果详情请求，回测ID: {backtest_id}")
        
        # 获取回测结果详情
        result = backtest_service.analyze_backtest(backtest_id)
        
        if result and result.get("status") == "success":
            logger.info(f"成功获取回测结果详情，回测ID: {backtest_id}")
            return ApiResponse(
                code=0,
                message="获取回测结果详情成功",
                data=result
            )
        else:
            logger.error(f"获取回测结果详情失败，回测ID: {backtest_id}")
            return ApiResponse(
                code=1,
                message="获取回测结果详情失败",
                data={}
            )
    except Exception as e:
        logger.error(f"获取回测结果详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.get("/{backtest_id}/replay", response_model=ApiResponse)
def get_replay_data(backtest_id: str):
    """
    获取回测回放数据
    
    Args:
        backtest_id: 回测ID
        
    Returns:
        ApiResponse: API响应，包含回测回放数据
    """
    try:
        logger.info(f"获取回测回放数据请求，回测ID: {backtest_id}")
        
        # 获取回测回放数据
        result = backtest_service.get_replay_data(backtest_id)
        
        if result and result.get("status") == "success":
            logger.info(f"成功获取回测回放数据，回测ID: {backtest_id}")
            return ApiResponse(
                code=0,
                message="获取回测回放数据成功",
                data=result
            )
        else:
            logger.error(f"获取回测回放数据失败，回测ID: {backtest_id}")
            return ApiResponse(
                code=1,
                message="获取回测回放数据失败",
                data={}
            )
    except Exception as e:
        logger.error(f"获取回测回放数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册回测API路由
router.include_router(router_backtest)
