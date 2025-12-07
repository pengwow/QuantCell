# 数据相关API路由

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Request, Depends
from typing import Optional, Dict, List, Any
from loguru import logger
from sqlalchemy.orm import Session

from ..schemas import ApiResponse
from ..db.database import get_db
from ..schemas.data import (
    DataInfoResponse,
    CalendarInfoResponse,
    InstrumentInfoResponse,
    FeatureInfoResponse,
    LoadDataRequest,
    SymbolFeaturesResponse,
    DataResponse,
    DownloadCryptoRequest,
    TaskStatusResponse,
    TaskProgressResponse,
    TaskResponse
)
from ..data_loader import data_loader
from ..utils.task_manager import task_manager

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
        from ..db import SystemConfig
        
        logger.info("开始加载QLib数据")
        
        # 从系统配置表中获取qlib_dir配置
        qlib_dir = SystemConfig.get("qlib_data_dir")
        
        if not qlib_dir:
            # 如果配置不存在，使用默认值
            qlib_dir = "data/qlib_data"
            logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
        
        logger.info(f"从系统配置获取QLib数据目录: {qlib_dir}")
        
        # 调用数据加载器加载数据
        success = data_loader.init_qlib(qlib_dir)
        
        if success:
            logger.info(f"QLib数据加载成功，目录: {qlib_dir}")
            
            # 获取加载的数据信息
            data_info = data_loader.get_loaded_data_info()
            
            return ApiResponse(
                code=0,
                message="数据加载成功",
                data=data_info
            )
        else:
            logger.error(f"QLib数据加载失败，目录: {qlib_dir}")
            return ApiResponse(
                code=1,
                message="数据加载失败",
                data={"qlib_dir": qlib_dir}
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
        logger.info("开始获取已加载的数据信息")
        
        # 获取已加载的数据信息
        data_info = data_loader.get_loaded_data_info()
        
        logger.info("成功获取已加载的数据信息")
        
        return ApiResponse(
            code=0,
            message="获取数据信息成功",
            data=data_info
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
        logger.info(f"开始获取交易日历信息，频率: {freq}, 开始时间: {start_time}, 结束时间: {end_time}")
        
        # 确保QLib已初始化
        if not data_loader.is_data_loaded():
            logger.info("QLib数据未加载，开始加载数据")
            
            # 从系统配置获取qlib_data_dir
            from ..db import SystemConfigBusiness as SystemConfig
            qlib_dir = SystemConfig.get("qlib_data_dir")
            
            if not qlib_dir:
                qlib_dir = "data/crypto_data"
                logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
            
            # 初始化QLib
            success = data_loader.init_qlib(qlib_dir)
            if not success:
                logger.error("QLib初始化失败，无法获取交易日历")
                return ApiResponse(
                    code=1,
                    message="QLib初始化失败，无法获取交易日历",
                    data={}
                )
        
        # 获取已加载的日历数据
        calendars = data_loader.get_calendars()
        logger.info(f"从data_loader获取到的日历数据: {list(calendars.keys())}")
        
        # 处理频率参数
        target_freq = freq if freq else "1d"
        
        # 如果请求的频率不在已加载的日历中，尝试获取
        if target_freq not in calendars:
            logger.info(f"请求的频率{target_freq}不在已加载的日历中，尝试获取")
            
            # 导入D类
            from qlib.data import D
            logger.info("D类已成功导入")
            
            # 直接调用D.calendar()获取日历数据
            calendar_dates = D.calendar(
                freq=target_freq,
                start_time=start_time,
                end_time=end_time
            )
            logger.info(f"成功调用D.calendar()，获取到{len(calendar_dates)}个交易日")
            
            # 将numpy.ndarray转换为Python标准类型列表，将Timestamp对象转换为字符串
            calendar_list = []
            for date in calendar_dates:
                try:
                    # 转换Timestamp对象为字符串格式
                    date_str = str(date)
                    calendar_list.append(date_str)
                except Exception as e:
                    logger.warning(f"转换日期时出现异常: {e}, 日期: {date}")
                    continue
            
            # 将获取到的日历添加到已加载的日历中
            calendars[target_freq] = calendar_list
            calendar_dates = calendar_list
        else:
            # 使用已加载的日历数据
            calendar_dates = calendars[target_freq]
            logger.info(f"使用已加载的日历数据，频率: {target_freq}，共{len(calendar_dates)}个交易日")
        
        # 构建响应
        calendar = {
            "freq": target_freq,
            "dates": calendar_dates,
            "count": len(calendar_dates)
        }
        
        return ApiResponse(
            code=0,
            message="获取交易日历成功",
            data=calendar
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
        logger.info(f"开始获取成分股信息，指数名称: {index_name}")
        
        # 获取所有成分股
        instruments = data_loader.get_instruments()
        
        if index_name:
            # 获取指定指数的成分股
            if index_name in instruments:
                instrument = {
                    "index_name": index_name,
                    "symbols": instruments[index_name],
                    "count": len(instruments[index_name])
                }
                return ApiResponse(
                    code=0,
                    message="获取成分股成功",
                    data=instrument
                )
            else:
                return ApiResponse(
                    code=1,
                    message=f"未找到指数{index_name}的成分股信息",
                    data={"index_name": index_name}
                )
        else:
            # 返回所有成分股
            result = {
                "instruments": []
            }
            for idx, symbols in instruments.items():
                result["instruments"].append({
                    "index_name": idx,
                    "symbols": symbols,
                    "count": len(symbols)
                })
            
            return ApiResponse(
                code=0,
                message="获取所有成分股成功",
                data=result
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
        logger.info(f"开始获取特征信息，货币名称: {symbol}")
        
        from ..db import crud
        
        if symbol:
            # 获取指定货币的特征
            features = crud.get_features_by_symbol(db, symbol)
            
            # 格式化特征信息
            feature_info = {
                "symbol": symbol,
                "features": [{
                    "feature_name": f.feature_name,
                    "freq": f.freq
                } for f in features],
                "count": len(features)
            }
            return ApiResponse(
                code=0,
                message="获取货币特征成功",
                data=feature_info
            )
        else:
            # 获取所有货币的特征
            features = crud.get_features(db)
            
            # 按货币名称分组
            features_by_symbol = {}
            for f in features:
                if f.symbol not in features_by_symbol:
                    features_by_symbol[f.symbol] = []
                features_by_symbol[f.symbol].append({
                    "feature_name": f.feature_name,
                    "freq": f.freq
                })
            
            # 返回所有货币的特征
            result = {
                "features": []
            }
            for sym, feats in features_by_symbol.items():
                result["features"].append({
                    "symbol": sym,
                    "features": feats,
                    "count": len(feats)
                })
            
            return ApiResponse(
                code=0,
                message="获取所有特征成功",
                data=result
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
        logger.info(f"开始获取货币{symbol}的特征数据")
        
        from ..db import crud
        
        # 获取指定货币的特征
        features = crud.get_features_by_symbol(db, symbol)
        
        # 格式化特征信息
        feature_info = {
            "symbol": symbol,
            "features": [{
                "feature_name": f.feature_name,
                "freq": f.freq
            } for f in features],
            "count": len(features)
        }
        
        logger.info(f"成功获取货币{symbol}的特征数据，共{len(features)}个特征")
        
        return ApiResponse(
            code=0,
            message="获取货币特征成功",
            data=feature_info
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
        logger.info("开始获取数据服务状态")
        
        # 获取数据加载状态
        data_loaded = data_loader.is_data_loaded()
        qlib_dir = data_loader.get_qlib_dir()
        
        status = {
            "data_loaded": data_loaded,
            "qlib_dir": qlib_dir,
            "status": "running"
        }
        
        logger.info(f"成功获取数据服务状态: {status}")
        
        return ApiResponse(
            code=0,
            message="获取数据服务状态成功",
            data=status
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
        logger.info("开始获取QLib状态")
        
        # 获取QLib状态
        data_loaded = data_loader.is_data_loaded()
        qlib_dir = data_loader.get_qlib_dir()
        
        # 获取已加载的数据信息
        data_info = data_loader.get_loaded_data_info()
        
        qlib_status = {
            "initialized": data_loaded,
            "qlib_dir": qlib_dir,
            "data_info": data_info
        }
        
        logger.info(f"成功获取QLib状态: {qlib_status}")
        
        return ApiResponse(
            code=0,
            message="获取QLib状态成功",
            data=qlib_status
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
        logger.info("开始重新加载QLib")
        
        # 从系统配置获取qlib_data_dir
        from ..db import SystemConfigBusiness as SystemConfig
        qlib_dir = SystemConfig.get("qlib_data_dir")
        
        if not qlib_dir:
            qlib_dir = "data/crypto_data"
            logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
        
        # 重新初始化QLib
        success = data_loader.init_qlib(qlib_dir)
        
        if success:
            logger.info(f"QLib重新加载成功，数据目录: {qlib_dir}")
            
            # 获取已加载的数据信息
            data_info = data_loader.get_loaded_data_info()
            
            return ApiResponse(
                code=0,
                message="QLib重新加载成功",
                data={
                    "qlib_dir": qlib_dir,
                    "data_info": data_info
                }
            )
        else:
            logger.error(f"QLib重新加载失败，数据目录: {qlib_dir}")
            return ApiResponse(
                code=1,
                message="QLib重新加载失败",
                data={
                    "qlib_dir": qlib_dir
                }
            )
    except Exception as e:
        logger.error(f"QLib重新加载失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


# 异步下载任务函数
def async_download_crypto(task_id: str, request: DownloadCryptoRequest):
    """异步下载加密货币数据
    
    Args:
        task_id: 任务ID
        request: 下载加密货币数据请求
    """
    try:
        from ..scripts.get_data import GetData
        from pathlib import Path
        
        logger.info(f"开始异步下载加密货币数据，任务ID: {task_id}, 请求参数: {request.model_dump()}")
        
        # 开始任务
        task_manager.start_task(task_id)
        
        # 实例化GetData类
        get_data = GetData()
        
        # 定义进度回调函数
        def progress_callback(current, completed, total, failed, status=None):
            """进度回调函数
            
            Args:
                current: 当前处理的项目
                completed: 已完成的项目数
                total: 总项目数
                failed: 失败的项目数
                status: 详细的状态描述，例如"Downloaded 2025-11-01"
            """
            # 计算进度百分比
            progress = 0
            if total > 0:
                progress = (completed / total) * 100
            
            # 更新任务进度，传递详细的状态描述
            task_manager.update_progress(task_id, current, completed, total, failed, status)
        
        # 处理保存目录：根据接口类型拼接路径
        save_dir = request.save_dir
        if save_dir:
            # 使用Path对象处理路径，拼接crypto类型
            save_dir = Path(save_dir) / "crypto"
            logger.info(f"拼接后的保存目录: {save_dir}")
        
        # 从数据库中读取qlib_data_dir配置
        from ..db import SystemConfigBusiness as SystemConfig
        qlib_dir = SystemConfig.get("qlib_data_dir")
        if not qlib_dir:
            qlib_dir = "data/crypto_data"
            logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
        else:
            logger.info(f"从数据库中读取到qlib_data_dir: {qlib_dir}")
        
        # 遍历所有时间周期
        for interval in request.interval:
            logger.info(f"开始处理时间周期: {interval}")
            
            # 调用crypto方法下载数据
            get_data.crypto(
                exchange=request.exchange,
                save_dir=str(save_dir) if save_dir else None,  # 传递拼接后的save_dir参数，GetData会自动在后面添加时间周期目录
                start=request.start,
                end=request.end,
                interval=interval,  # 使用当前时间周期
                max_workers=request.max_workers,
                candle_type=request.candle_type,
                symbols=",".join(request.symbols),
                convert_to_qlib=True,
                qlib_dir=qlib_dir,  # 传递从数据库读取的qlib_data_dir作为转换地址
                progress_callback=progress_callback
            )
            
            logger.info(f"时间周期 {interval} 数据下载成功")
        
        logger.info(f"所有时间周期数据下载成功，任务ID: {task_id}")
        
        # 更新任务状态为已完成
        task_manager.complete_task(task_id)
    except Exception as e:
        logger.error(f"加密货币数据下载失败，任务ID: {task_id}, 错误: {e}")
        logger.exception(e)
        
        # 更新任务状态为失败
        task_manager.fail_task(task_id, error=str(e))


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
        logger.info(f"收到加密货币数据下载请求，参数: {request.model_dump()}")
        
        # 如果没有接收到save_dir，则从数据库中读取
        if not request.save_dir:
            from ..db import SystemConfigBusiness as SystemConfig
            logger.info("没有接收到save_dir，从数据库中读取data_download_dir")
            data_download_dir = SystemConfig.get("data_download_dir")
            if data_download_dir:
                logger.info(f"从数据库中读取到data_download_dir: {data_download_dir}")
                request.save_dir = data_download_dir
            else:
                logger.warning("数据库中未找到data_download_dir配置")
        
        # 创建下载任务
        task_id = task_manager.create_task(
            task_type="download_crypto",
            exchange=request.exchange,
            start=request.start,
            end=request.end,
            interval=request.interval,  # 使用所有时间周期
            max_workers=request.max_workers,
            candle_type=request.candle_type,
            symbols=request.symbols,
            save_dir=request.save_dir
        )
        
        logger.info(f"创建下载任务成功，任务ID: {task_id}")
        
        # 将下载任务添加到后台任务
        background_tasks.add_task(async_download_crypto, task_id, request)
        
        return ApiResponse(
            code=0,
            message="加密货币数据下载任务已创建",
            data={
                "task_id": task_id,
                "message": "下载任务已创建，可通过 /api/data/task/{task_id} 查询进度"
            }
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
        logger.info(f"查询任务状态，任务ID: {task_id}")
        
        # 获取任务状态
        task_info = task_manager.get_task(task_id)
        
        if not task_info:
            logger.warning(f"任务不存在，任务ID: {task_id}")
            return ApiResponse(
                code=1,
                message="任务不存在",
                data={"task_id": task_id}
            )
        
        logger.info(f"查询任务状态成功，任务ID: {task_id}, 状态: {task_info['status']}")
        
        return ApiResponse(
            code=0,
            message="查询任务状态成功",
            data=task_info
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
        logger.info(f"开始获取加密货币对列表，交易所: {exchange}, 过滤条件: {filter}, 限制: {limit}, 偏移: {offset}")
        
        # 导入ccxt库
        import ccxt
        
        # 从应用上下文中读取代理配置
        configs = request.app.state.configs
        
        # 读取代理配置
        proxy_enabled = configs.get("proxy_enabled") == "true"
        proxy_url = configs.get("proxy_url")
        proxy_username = configs.get("proxy_username")
        proxy_password = configs.get("proxy_password")
        # configs.get("proxy_timeout")
        
        logger.info(f"代理配置: enabled={proxy_enabled}, url={proxy_url}")
        
        # 创建交易所实例
        exchange_instance = getattr(ccxt, exchange)()
        # 添加超时设置
        exchange_instance.timeout = 10000  # 10秒超时
        
        # 如果启用代理，设置代理参数
        if proxy_enabled and proxy_url:
            # 处理代理认证
            if proxy_username and proxy_password:
                # 构建带认证的代理URL
                from urllib.parse import urlparse
                parsed_url = urlparse(proxy_url)
                proxy_with_auth = f"{parsed_url.scheme}://{proxy_username}:{proxy_password}@{parsed_url.netloc}{parsed_url.path}"
                exchange_instance.proxy = proxy_with_auth
                logger.info(f"使用带认证的代理: {proxy_with_auth}")
            else:
                # 使用不带认证的代理
                exchange_instance.proxies = {
                    'https': proxy_url,
                    'http': proxy_url
                }
                # exchange_instance.proxy = proxy_url
                logger.info(f"使用不带认证的代理: {proxy_url}")
        else:
            logger.info("未启用代理")
        
        logger.info(f"成功创建{exchange}交易所实例")
        
        # 获取货币对列表，添加错误处理
        try:
            markets = exchange_instance.fetch_markets()
            logger.info(f"成功获取{exchange}交易所的货币对列表，共{len(markets)}个货币对")
        except Exception as e:
            logger.error(f"调用{exchange}.fetch_markets()失败: {e}")
            # 返回友好的错误信息给客户端
            return ApiResponse(
                code=1,
                message=f"获取{exchange}交易所货币对列表失败，请检查网络连接或交易所状态",
                data={
                    "error": str(e),
                    "exchange": exchange
                }
            )
        
        # 处理货币对列表
        symbols = []
        for market in markets:
            # 过滤无效或不活跃的货币对
            if not market.get("active", True):
                continue
            
            # 提取必要的信息
            symbol_info = {
                "symbol": market.get("symbol"),
                "base": market.get("base"),
                "quote": market.get("quote"),
                "active": market.get("active"),
                "precision": market.get("precision"),
                "limits": market.get("limits"),
                "type": market.get("type")
            }
            
            # 应用过滤条件
            if filter:
                if filter not in symbol_info["symbol"]:
                    continue
            
            symbols.append(symbol_info)
        
        # 实现分页
        paginated_symbols = symbols[offset:offset+limit]
        
        logger.info(f"处理完成，共{len(symbols)}个符合条件的货币对，返回{len(paginated_symbols)}个货币对")
        
        # 构建响应
        response_data = {
            "symbols": paginated_symbols,
            "total": len(symbols),
            "offset": offset,
            "limit": limit,
            "exchange": exchange
        }
        
        return ApiResponse(
            code=0,
            message="获取加密货币对列表成功",
            data=response_data
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
        logger.info(f"查询任务列表请求: page={page}, page_size={page_size}, task_type={task_type}, status={status}")
        
        # 转换时间字符串为datetime对象
        from datetime import datetime
        
        # 处理开始时间
        start_time_dt = None
        if start_time:
            try:
                start_time_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的开始时间格式: {start_time}，忽略该过滤条件")
        
        # 处理结束时间
        end_time_dt = None
        if end_time:
            try:
                end_time_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的结束时间格式: {end_time}，忽略该过滤条件")
        
        # 处理创建时间
        created_at_dt = None
        if created_at:
            try:
                created_at_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的创建时间格式: {created_at}，忽略该过滤条件")
        
        # 处理更新时间
        updated_at_dt = None
        if updated_at:
            try:
                updated_at_dt = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"无效的更新时间格式: {updated_at}，忽略该过滤条件")
        
        # 计算偏移量
        skip = (page - 1) * page_size
        
        # 使用SQLAlchemy CRUD操作获取数据
        from ..db import crud
        tasks, total = crud.get_tasks_paginated(
            db=db,
            skip=skip,
            limit=page_size,
            task_type=task_type,
            status=status,
            start_time=start_time_dt,
            end_time=end_time_dt,
            created_at=created_at_dt,
            updated_at=updated_at_dt,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # 计算总页数
        pages = (total + page_size - 1) // page_size
        
        # 构建响应数据
        # 转换SQLAlchemy模型为字典格式
        import json
        task_list = []
        for task in tasks:
            task_dict = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status,
                "progress": {
                    "total": task.total,
                    "completed": task.completed,
                    "failed": task.failed,
                    "current": task.current,
                    "percentage": task.percentage
                },
                "params": json.loads(task.params),
                "start_time": task.start_time,
                "end_time": task.end_time,
                "error_message": task.error_message,
                "created_at": task.created_at,
                "updated_at": task.updated_at
            }
            task_list.append(task_dict)
        
        result = {
            "tasks": task_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": pages
            }
        }
        
        logger.info(f"查询任务列表成功: 共{total}条，第{page}/{pages}页")
        
        return ApiResponse(
            code=0,
            message="查询任务列表成功",
            data=result
        )
    except Exception as e:
        logger.error(f"查询任务列表失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))
