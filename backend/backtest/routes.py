# 回测服务API路由

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

# 导入JWT认证装饰器
from utils.auth import jwt_auth_required_sync

from backtest.schemas import (ApiResponse, BacktestAnalyzeRequest,
                      BacktestDeleteRequest, BacktestListRequest,
                      BacktestRunRequest, StrategyConfigRequest,
                      BacktestReplayRequest, DataIntegrityCheckRequest,
                      DataIntegrityCheckResponse, DataDownloadResponse,
                      BacktestStopRequest)
from strategy.schemas import StrategyUploadRequest
from backtest.service import BacktestService

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
        
        if result.get("status") == "failed":
            return ApiResponse(
                code=1,
                message=result.get("message", "回测执行失败"),
                data=result
            )
        
        return ApiResponse(
            code=0,
            message="回测执行成功",
            data=result
        )
    except Exception as e:
        logger.error(f"回测执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post(
    "/stop",
    response_model=ApiResponse,
    summary="终止回测",
    description="终止正在进行的回测任务",
    responses={
        200: {"description": "回测终止成功"},
        404: {"description": "回测任务不存在"},
        500: {"description": "终止回测失败"}
    }
)
def stop_backtest(request: BacktestStopRequest):
    """
    终止回测
    
    Args:
        request: 终止回测请求参数，包含任务ID
        
    Returns:
        ApiResponse: API响应，包含终止结果
    """
    try:
        logger.info(f"终止回测请求，任务ID: {request.task_id}")
        
        # 调用服务层终止回测
        result = backtest_service.stop_backtest(request.task_id)
        
        logger.info(f"回测终止完成，结果: {result}")
        
        if result.get("status") == "success":
            return ApiResponse(
                code=0,
                message="回测已终止",
                data=result
            )
        else:
            return ApiResponse(
                code=1,
                message=result.get("message", "终止回测失败"),
                data=result
            )
    except Exception as e:
        logger.error(f"终止回测失败: {e}")
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
@jwt_auth_required_sync
def delete_backtest(request: Request, backtest_id: str):
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


@router_backtest.get(
    "/{backtest_id}/symbols", 
    response_model=ApiResponse,
    summary="获取回测货币对列表",
    description="获取回测包含的所有货币对信息，用于多货币对切换展示",
    responses={
        200: {
            "description": "获取回测货币对列表成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 0,
                        "message": "获取回测货币对列表成功",
                        "data": {
                            "symbols": [
                                {
                                    "symbol": "BTCUSDT",
                                    "status": "success",
                                    "message": "回测成功"
                                },
                                {
                                    "symbol": "ETHUSDT",
                                    "status": "success",
                                    "message": "回测成功"
                                }
                            ],
                            "total": 2
                        }
                    }
                }
            }
        },
        500: {"description": "获取回测货币对列表失败"}
    }
)
def get_backtest_symbols(backtest_id: str):
    """
    获取回测包含的所有货币对信息
    
    Args:
        backtest_id: 回测ID
        
    Returns:
        ApiResponse: API响应，包含回测货币对列表
        
    Response Data Format:
        {
            "symbols": [
                {
                    "symbol": string,  # 货币对符号
                    "status": string,  # 回测状态，"success" 或 "failed"
                    "message": string  # 回测状态信息
                },
                # 更多货币对...
            ],
            "total": number  # 货币对总数
        }
    """
    try:
        logger.info(f"获取回测货币对列表请求，回测ID: {backtest_id}")
        
        # 获取回测货币对列表
        result = backtest_service.get_backtest_symbols(backtest_id)
        
        if result and result.get("status") == "success":
            logger.info(f"成功获取回测货币对列表，回测ID: {backtest_id}")
            return ApiResponse(
                code=0,
                message="获取回测货币对列表成功",
                data=result.get('data')
            )
        else:
            logger.error(f"获取回测货币对列表失败，回测ID: {backtest_id}")
            return ApiResponse(
                code=1,
                message="获取回测货币对列表失败",
                data={}
            )
    except Exception as e:
        logger.error(f"获取回测货币对列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.get(
    "/{backtest_id}/replay", 
    response_model=ApiResponse,
    summary="获取回测回放数据",
    description="获取回测回放数据，包含K线数据、交易信号和权益曲线数据",
    responses={
        200: {
            "description": "获取回测回放数据成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 0,
                        "message": "获取回测回放数据成功",
                        "data": {
                            "kline_data": [
                                {
                                    "time": "2024-01-01 00:00:00",
                                    "open": 100.0,
                                    "high": 105.0,
                                    "low": 95.0,
                                    "close": 102.0,
                                    "volume": 1000.0
                                }
                            ],
                            "trade_signals": [
                                {
                                    "time": "2024-01-01 10:00:00",
                                    "type": "buy",
                                    "price": 100.0,
                                    "size": 1.0,
                                    "trade_id": "123"
                                }
                            ],
                            "equity_data": [
                                {
                                    "time": "2024-01-01 00:00:00",
                                    "equity": 10000.0
                                }
                            ]
                        }
                    }
                }
            }
        },
        500: {"description": "获取回测回放数据失败"}
    }
)
def get_replay_data(backtest_id: str, symbol: Optional[str] = None):
    """
    获取回测回放数据
    
    Args:
        backtest_id: 回测ID
        symbol: 可选，指定货币对，用于多货币对回测结果
        
    Returns:
        ApiResponse: API响应，包含回测回放数据
        
    Response Data Format:
        {
            "kline_data": [
                {
                    "timestamp": number,  # 时间戳，毫秒级，与/data/klines接口保持一致
                    "open": number,       # 开盘价
                    "close": number,      # 收盘价
                    "high": number,       # 最高价
                    "low": number,        # 最低价
                    "volume": number,     # 成交量
                    "turnover": number    # 成交额（回测为0）
                },
                # 更多K线数据...
            ],
            "trade_signals": [
                {
                    "time": string,  # 交易时间，格式：YYYY-MM-DD HH:MM:SS
                    "type": string,  # 交易类型，"buy" 或 "sell"
                    "price": number, # 交易价格
                    "size": number,  # 交易大小
                    "trade_id": string # 交易ID
                },
                # 更多交易信号...
            ],
            "equity_data": [
                {
                    "time": string,  # 时间，格式：YYYY-MM-DD HH:MM:SS
                    "equity": number # 权益值
                },
                # 更多权益数据...
            ]
        }
    """
    try:
        logger.info(f"获取回测回放数据请求，回测ID: {backtest_id}, 货币对: {symbol}")
        
        # 获取回测回放数据
        result = backtest_service.get_replay_data(backtest_id, symbol)
        
        if result and result.get("status") == "success":
            logger.info(f"成功获取回测回放数据，回测ID: {backtest_id}")
            return ApiResponse(
                code=0,
                message="获取回测回放数据成功",
                data=result.get('data')
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


@router_backtest.post(
    "/check-data",
    response_model=DataIntegrityCheckResponse,
    summary="检查回测数据完整性",
    description="检查指定交易对在指定时间范围内的数据完整性",
    responses={
        200: {"description": "数据完整性检查完成"},
        500: {"description": "检查失败"}
    }
)
def check_data_integrity(request: DataIntegrityCheckRequest):
    """
    检查回测数据完整性
    
    Args:
        request: 数据完整性检查请求参数
        
    Returns:
        DataIntegrityCheckResponse: 检查结果
    """
    try:
        logger.info(f"数据完整性检查请求: {request.symbol} {request.interval}")
        
        from backtest.data_integrity import DataIntegrityChecker
        from datetime import datetime
        
        # 解析时间
        start_time = datetime.strptime(request.start_time, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(request.end_time, "%Y-%m-%d %H:%M:%S")
        
        # 执行检查
        checker = DataIntegrityChecker()
        result = checker.check_data_completeness(
            symbol=request.symbol,
            interval=request.interval,
            start_time=start_time,
            end_time=end_time,
            market_type=request.market_type,
            crypto_type=request.crypto_type
        )
        
        # 转换结果为响应格式
        response_data = {
            "is_complete": result.is_complete,
            "total_expected": result.total_expected,
            "total_actual": result.total_actual,
            "missing_count": result.missing_count,
            "missing_ranges": [
                {"start": start.isoformat(), "end": end.isoformat()}
                for start, end in result.missing_ranges
            ],
            "quality_issues": result.quality_issues,
            "coverage_percent": round(result.coverage_percent, 2)
        }
        
        logger.info(f"数据完整性检查完成: {request.symbol}, 覆盖率: {result.coverage_percent:.2f}%")
        
        return DataIntegrityCheckResponse(
            code=0,
            message="数据完整性检查完成",
            data=response_data
        )
    except Exception as e:
        logger.error(f"数据完整性检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_backtest.post(
    "/download-data",
    response_model=DataDownloadResponse,
    summary="下载缺失的回测数据",
    description="下载指定交易对在指定时间范围内的缺失数据",
    responses={
        200: {"description": "数据下载任务已启动"},
        500: {"description": "下载失败"}
    }
)
def download_missing_data(request: DataIntegrityCheckRequest):
    """
    下载缺失的回测数据
    
    Args:
        request: 数据下载请求参数
        
    Returns:
        DataDownloadResponse: 下载进度信息
    """
    try:
        logger.info(f"数据下载请求: {request.symbol} {request.interval}")
        
        from backtest.data_downloader import BacktestDataDownloader
        from datetime import datetime
        
        # 解析时间
        start_time = datetime.strptime(request.start_time, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(request.end_time, "%Y-%m-%d %H:%M:%S")
        
        # 创建下载器
        downloader = BacktestDataDownloader()
        
        # 执行下载（同步方式，会等待下载完成）
        success, result = downloader.ensure_data_complete(
            symbol=request.symbol,
            interval=request.interval,
            start_time=start_time,
            end_time=end_time,
            market_type=request.market_type,
            crypto_type=request.crypto_type,
            max_wait_time=300  # 最多等待5分钟
        )
        
        response_data = {
            "task_id": "sync_download",
            "symbol": request.symbol,
            "interval": request.interval,
            "status": "completed" if success else "failed",
            "progress": 100.0 if success else 0.0,
            "message": "数据下载完成" if success else "数据下载失败",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error": None if success else "下载失败或超时"
        }
        
        logger.info(f"数据下载完成: {request.symbol}, 成功: {success}")
        
        return DataDownloadResponse(
            code=0 if success else 1,
            message="数据下载完成" if success else "数据下载失败",
            data=response_data
        )
    except Exception as e:
        logger.error(f"数据下载失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册回测API路由
router.include_router(router_backtest)
