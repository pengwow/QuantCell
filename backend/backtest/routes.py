# 回测服务API路由

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from .schemas import (ApiResponse, BacktestAnalyzeRequest,
                      BacktestDeleteRequest, BacktestListRequest,
                      BacktestRunRequest, ExecutorConfigRequest,
                      StrategyConfigRequest)
from .service import BacktestService

# 创建API路由实例
router = APIRouter()

# 创建回测服务实例
backtest_service = BacktestService()

# 创建回测API路由子路由
router_backtest = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router_backtest.get("/list", response_model=ApiResponse)
def get_backtest_list():
    """
    获取所有回测结果列表
    
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
        
        # 获取策略类型列表
        strategies = backtest_service.get_strategy_list()
        
        logger.info(f"成功获取策略类型列表，共 {len(strategies)} 个策略类型")
        
        return ApiResponse(
            code=0,
            message="获取策略类型列表成功",
            data={"strategies": strategies}
        )
    except Exception as e:
        logger.error(f"获取策略类型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post("/run", response_model=ApiResponse)
def run_backtest(request: BacktestRunRequest):
    """
    执行回测
    
    Args:
        request: 回测执行请求参数，包含策略配置、执行器配置和回测配置
        
    Returns:
        ApiResponse: API响应，包含回测结果
    """
    try:
        logger.info("执行回测请求")
        
        # 执行回测
        result = backtest_service.run_backtest(
            strategy_config=request.strategy_config,
            executor_config=request.executor_config,
            backtest_config=request.backtest_config
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
        request: 回测分析请求参数，包含回测名称
        
    Returns:
        ApiResponse: API响应，包含回测分析结果
    """
    try:
        logger.info(f"分析回测结果请求，回测名称: {request.backtest_name}")
        
        # 分析回测结果
        result = backtest_service.analyze_backtest(request.backtest_name)
        
        logger.info(f"回测结果分析完成，结果: {result}")
        
        return ApiResponse(
            code=0,
            message="回测结果分析成功",
            data=result
        )
    except Exception as e:
        logger.error(f"回测结果分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.delete("/delete/{backtest_name}", response_model=ApiResponse)
def delete_backtest(backtest_name: str):
    """
    删除回测结果
    
    Args:
        backtest_name: 回测名称
        
    Returns:
        ApiResponse: API响应，包含回测删除结果
    """
    try:
        logger.info(f"删除回测结果请求，回测名称: {backtest_name}")
        
        # 删除回测结果
        result = backtest_service.delete_backtest_result(backtest_name)
        
        if result:
            logger.info(f"回测结果删除成功，回测名称: {backtest_name}")
            return ApiResponse(
                code=0,
                message="回测结果删除成功",
                data={"backtest_name": backtest_name, "result": result}
            )
        else:
            logger.warning(f"回测结果删除失败，回测名称: {backtest_name}")
            return ApiResponse(
                code=1,
                message="回测结果删除失败",
                data={"backtest_name": backtest_name, "result": result}
            )
    except Exception as e:
        logger.error(f"回测结果删除失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post("/strategy/config", response_model=ApiResponse)
def create_strategy_config(request: StrategyConfigRequest):
    """
    创建策略配置
    
    Args:
        request: 策略配置请求参数，包含策略类型和参数
        
    Returns:
        ApiResponse: API响应，包含策略配置
    """
    try:
        logger.info(f"创建策略配置请求，策略类型: {request.strategy_type}")
        
        # 创建策略配置
        strategy_config = backtest_service.create_strategy_config(
            strategy_type=request.strategy_type,
            params=request.params
        )
        
        if strategy_config:
            logger.info(f"策略配置创建成功，策略类型: {request.strategy_type}")
            return ApiResponse(
                code=0,
                message="策略配置创建成功",
                data={"strategy_config": strategy_config}
            )
        else:
            logger.error(f"策略配置创建失败，策略类型: {request.strategy_type}")
            return ApiResponse(
                code=1,
                message="策略配置创建失败",
                data={}
            )
    except Exception as e:
        logger.error(f"策略配置创建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post("/executor/config", response_model=ApiResponse)
def create_executor_config(request: ExecutorConfigRequest):
    """
    创建执行器配置
    
    Args:
        request: 执行器配置请求参数，包含执行器类型和参数
        
    Returns:
        ApiResponse: API响应，包含执行器配置
    """
    try:
        logger.info(f"创建执行器配置请求，执行器类型: {request.executor_type}")
        
        # 创建执行器配置
        executor_config = backtest_service.create_executor_config(
            executor_type=request.executor_type,
            params=request.params
        )
        
        if executor_config:
            logger.info(f"执行器配置创建成功，执行器类型: {request.executor_type}")
            return ApiResponse(
                code=0,
                message="执行器配置创建成功",
                data={"executor_config": executor_config}
            )
        else:
            logger.error(f"执行器配置创建失败，执行器类型: {request.executor_type}")
            return ApiResponse(
                code=1,
                message="执行器配置创建失败",
                data={}
            )
    except Exception as e:
        logger.error(f"执行器配置创建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册回测API路由
router.include_router(router_backtest)
