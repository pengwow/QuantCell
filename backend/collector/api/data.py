# 数据相关API路由

from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request)
from loguru import logger
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..schemas import ApiResponse
from ..schemas.data import (CalendarInfoResponse, DataInfoResponse,
                            DataResponse, DownloadCryptoRequest,
                            FeatureInfoResponse, InstrumentInfoResponse,
                            LoadDataRequest, SymbolFeaturesResponse,
                            TaskProgressResponse, TaskResponse,
                            TaskStatusResponse)
from ..services import DataService

# 创建API路由实例
router = APIRouter(prefix="/api/data", tags=["data-management"])


@router.post("/load", response_model=ApiResponse)
def load_data(request: LoadDataRequest):
    """加载QLib数据
    
    从系统配置表中获取qlib_dir配置，加载QLib格式的数据
    
    Args:
        request: 加载数据请求，不需要任何参数
        
    Returns:
        ApiResponse: 包含加载结果的响应
    """
    try:
        data_service = DataService()
        result = data_service.load_data(request)
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["data_info"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={"qlib_dir": result["qlib_dir"]}
            )
    except Exception as e:
        logger.error(f"加载数据失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info", response_model=ApiResponse)
def get_data_info():
    """获取已加载的数据信息
    
    Returns:
        ApiResponse: 包含已加载数据信息的响应
    """
    try:
        data_service = DataService()
        result = data_service.get_data_info()
        
        return ApiResponse(
            code=0,
            message="获取数据信息成功",
            data=result
        )
    except Exception as e:
        logger.error(f"获取数据信息失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendars", response_model=ApiResponse)
def get_calendars(
    freq: Optional[str] = Query(None, description="频率，如'day'、'1min'、'1m'等"),
    start_time: Optional[str] = Query(None, description="开始时间，格式YYYY-MM-DD HH:mm:SS"),
    end_time: Optional[str] = Query(None, description="结束时间，格式YYYY-MM-DD HH:mm:SS")
):
    """获取交易日历信息
    
    Args:
        freq: 可选，指定频率，如'day'、'1min'、'1m'等
        start_time: 可选，开始时间，格式YYYY-MM-DD HH:mm:SS
        end_time: 可选，结束时间，格式YYYY-MM-DD HH:mm:SS
        
    Returns:
        ApiResponse: 包含交易日历信息的响应
    """
    try:
        data_service = DataService()
        result = data_service.get_calendars(freq, start_time, end_time)
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["calendar"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={}
            )
    except Exception as e:
        logger.error(f"获取交易日历失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instruments", response_model=ApiResponse)
def get_instruments(index_name: Optional[str] = Query(None, description="指数名称")):
    """获取成分股信息
    
    Args:
        index_name: 可选，指定指数名称
        
    Returns:
        ApiResponse: 包含成分股信息的响应
    """
    try:
        data_service = DataService()
        result = data_service.get_instruments(index_name)
        
        if result["success"]:
            if index_name:
                return ApiResponse(
                    code=0,
                    message=result["message"],
                    data=result["instrument"]
                )
            else:
                return ApiResponse(
                    code=0,
                    message=result["message"],
                    data=result["result"]
                )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={"index_name": result["index_name"]}
            )
    except Exception as e:
        logger.error(f"获取成分股失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features", response_model=ApiResponse)
def get_features(
    symbol: Optional[str] = Query(None, description="货币名称"),
    db: Session = Depends(get_db)
):
    """获取特征信息
    
    Args:
        symbol: 可选，指定货币名称
        db: 数据库会话依赖
        
    Returns:
        ApiResponse: 包含特征信息的响应
    """
    try:
        data_service = DataService(db)
        result = data_service.get_features(symbol)
        
        if result["success"]:
            if symbol:
                return ApiResponse(
                    code=0,
                    message=result["message"],
                    data=result["feature_info"]
                )
            else:
                return ApiResponse(
                    code=0,
                    message=result["message"],
                    data=result["result"]
                )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={}
            )
    except Exception as e:
        logger.error(f"获取特征失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features/{symbol}", response_model=ApiResponse)
def get_symbol_features(
    symbol: str,
    db: Session = Depends(get_db)
):
    """获取指定货币的特征数据
    
    Args:
        symbol: 货币名称
        db: 数据库会话依赖
        
    Returns:
        ApiResponse: 包含指定货币特征数据的响应
    """
    try:
        data_service = DataService(db)
        result = data_service.get_symbol_features(symbol)
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["feature_info"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={}
            )
    except Exception as e:
        logger.error(f"获取货币特征失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=ApiResponse)
def get_data_status():
    """获取数据服务状态
    
    Returns:
        ApiResponse: 包含数据服务状态的响应
    """
    try:
        data_service = DataService()
        result = data_service.get_data_status()
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["status"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={}
            )
    except Exception as e:
        logger.error(f"获取数据服务状态失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qlib/status", response_model=ApiResponse)
def get_qlib_status():
    """获取QLib状态
    
    Returns:
        ApiResponse: 包含QLib状态的响应
    """
    try:
        data_service = DataService()
        result = data_service.get_qlib_status()
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["qlib_status"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={}
            )
    except Exception as e:
        logger.error(f"获取QLib状态失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/qlib/reload", response_model=ApiResponse)
def reload_qlib():
    """重新加载QLib
    
    Returns:
        ApiResponse: 包含重新加载结果的响应
    """
    try:
        data_service = DataService()
        result = data_service.reload_qlib()
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data={
                    "qlib_dir": result["qlib_dir"],
                    "data_info": result["data_info"]
                }
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={
                    "qlib_dir": result["qlib_dir"]
                }
            )
    except Exception as e:
        logger.error(f"QLib重新加载失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/crypto", response_model=ApiResponse)
def download_crypto(request: DownloadCryptoRequest, background_tasks: BackgroundTasks):
    """下载加密货币数据（异步）
    
    Args:
        request: 下载加密货币数据请求
        background_tasks: FastAPI后台任务对象
        
    Returns:
        ApiResponse: 包含任务ID的响应，用于查询下载进度
    """
    try:
        data_service = DataService()
        result = data_service.create_download_task(request)
        
        if result["success"]:
            # 将下载任务添加到后台任务
            background_tasks.add_task(DataService.async_download_crypto, result["task_id"], request)
            
            return ApiResponse(
                code=0,
                message=result["message"],
                data={
                    "task_id": result["task_id"],
                    "message": "下载任务已创建，可通过 /api/data/task/{task_id} 查询进度"
                }
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={}
            )
    except Exception as e:
        logger.error(f"创建加密货币数据下载任务失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}", response_model=ApiResponse)
def get_task_status(task_id: str):
    """查询任务状态
    
    Args:
        task_id: 任务ID
        
    Returns:
        ApiResponse: 包含任务状态和进度的响应
    """
    try:
        data_service = DataService()
        result = data_service.get_task_status(task_id)
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["task_info"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={"task_id": result["task_id"]}
            )
    except Exception as e:
        logger.error(f"查询任务状态失败，任务ID: {task_id}, 错误: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crypto/symbols", response_model=ApiResponse)
def get_crypto_symbols(
    request: Request,
    exchange: str = Query(default="binance", description="交易所名称，如binance、okx等"),
    filter: Optional[str] = Query(default=None, description="过滤条件，如'USDT'表示只返回USDT交易对"),
    limit: Optional[int] = Query(default=100, description="返回数量限制"),
    offset: Optional[int] = Query(default=0, description="返回偏移量")
):
    """获取加密货币对列表
    
    Args:
        request: FastAPI请求对象，用于访问应用实例
        exchange: 交易所名称，如binance、okx等
        filter: 过滤条件，如'USDT'表示只返回USDT交易对
        limit: 返回数量限制
        offset: 返回偏移量
        
    Returns:
        ApiResponse: 包含货币对列表的响应
    """
    try:
        data_service = DataService()
        configs = request.app.state.configs
        result = data_service.get_crypto_symbols(exchange, filter, limit, offset, configs)
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["response_data"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={
                    "error": result["error"],
                    "exchange": result["exchange"]
                }
            )
    except Exception as e:
        logger.error(f"获取加密货币对列表失败: {e}")
        logger.exception(e)
        # 返回友好的错误信息给客户端
        return ApiResponse(
            code=1,
            message="获取加密货币对列表失败，请检查参数或稍后重试",
            data={
                "error": str(e),
                "exchange": exchange
            }
        )


@router.get("/tasks", response_model=ApiResponse)
def get_all_tasks(
    page: int = Query(1, ge=1, description="当前页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    task_type: Optional[str] = Query(None, description="任务类型"),
    status: Optional[str] = Query(None, description="任务状态"),
    start_time: Optional[str] = Query(None, description="开始时间，格式YYYY-MM-DD HH:MM:SS"),
    end_time: Optional[str] = Query(None, description="结束时间，格式YYYY-MM-DD HH:MM:SS"),
    created_at: Optional[str] = Query(None, description="创建时间，格式YYYY-MM-DD HH:MM:SS"),
    updated_at: Optional[str] = Query(None, description="更新时间，格式YYYY-MM-DD HH:MM:SS"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序顺序，asc或desc"),
    db: Session = Depends(get_db)
):
    """查询所有任务状态，支持分页和过滤
    
    Args:
        page: 当前页码
        page_size: 每页数量
        task_type: 任务类型过滤
        status: 任务状态过滤
        start_time: 开始时间过滤
        end_time: 结束时间过滤
        created_at: 创建时间过滤
        updated_at: 更新时间过滤
        sort_by: 排序字段
        sort_order: 排序顺序
        db: 数据库会话
        
    Returns:
        ApiResponse: 包含任务列表和分页信息的响应
    """
    try:
        data_service = DataService(db)
        result = data_service.get_all_tasks(
            page=page,
            page_size=page_size,
            task_type=task_type,
            status=status,
            start_time=start_time,
            end_time=end_time,
            created_at=created_at,
            updated_at=updated_at,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["result"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={}
            )
    except Exception as e:
        logger.error(f"查询任务列表失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/klines", response_model=ApiResponse)
def get_klines(
    symbol: str = Query(..., description="货币对"),
    interval: str = Query(..., description="周期"),
    start_time: Optional[str] = Query(None, description="开始时间，格式YYYY-MM-DD HH:MM:SS"),
    end_time: Optional[str] = Query(None, description="结束时间，格式YYYY-MM-DD HH:MM:SS"),
    limit: Optional[int] = Query(1000, ge=1, le=10000, description="返回数量限制"),
    db: Session = Depends(get_db)
):
    """获取K线数据
    
    从数据库中查询指定货币对和周期的K线数据
    
    Args:
        symbol: 货币对
        interval: 周期
        start_time: 开始时间，格式YYYY-MM-DD HH:MM:SS
        end_time: 结束时间，格式YYYY-MM-DD HH:MM:SS
        limit: 返回数量限制
        db: 数据库会话
        
    Returns:
        ApiResponse: 包含K线数据的响应
    """
    try:
        data_service = DataService(db)
        result = data_service.get_kline_data(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["kline_data"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data=[]
            )
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))
