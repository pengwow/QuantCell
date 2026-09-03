# 数据相关API路由


from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
)

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

from ..db.database import get_db
from ..db.models import CryptoFutureKline, CryptoSpotKline, StockKline
from ..schemas import ApiResponse
from ..services import DataService
from ..services.kline_health_service import KlineHealthChecker

# 创建API路由实例
router = APIRouter(prefix="/data", tags=["data-management"])

# 数据质量相关API
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..schemas.data import (
        DownloadCryptoRequest,
        ExportCryptoRequest,
    )

# 创建数据质量API子路由
quality_router = APIRouter(prefix="/quality", tags=["data-quality"])


@quality_router.get("/options", response_model=ApiResponse)
async def get_quality_options(
    symbol: str | None = Query(None, description="货币对，如BTCUSDT，为空时返回所有可用货币对"),
    market_type: str = Query(
        "crypto",
        description="市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）",
    ),
    crypto_type: str = Query(
        "spot",
        description="加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）",
    ),
):
    """
    获取数据质量检查的下拉选项API

    用于获取数据质量检查页面的货币对和时间周期下拉选项数据
    当symbol为空时，返回所有可用货币对及其对应的时间周期列表
    当symbol不为空时，返回该货币对的可用时间周期列表

    返回示例：
    {
      "code": 0,
      "message": "获取下拉选项数据成功",
      "data": {
        "BTCUSDT": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        "ETHUSDT": ["1m", "5m", "1h", "1d"],
        "BNBUSDT": ["1h", "1d"]
      }
    }
    """
    try:
        from quality.parquet_provider import ParquetDataProvider

        provider = ParquetDataProvider()

        # 获取可用选项
        if symbol:
            formatted_symbol = symbol.replace("/", "")
            intervals = provider.get_available_intervals(formatted_symbol, crypto_type)
            response_data = {formatted_symbol: intervals}
        else:
            symbols = provider.list_available_symbols(candle_type=crypto_type)

            # 转换为前端期望的格式 {symbol: [intervals]}
            response_data = {}
            for sym_info in symbols:
                response_data[sym_info["symbol"]] = sym_info["intervals"]

        return ApiResponse(code=0, message="获取下拉选项数据成功", data=response_data)
    except Exception as e:
        logger.error(f"获取下拉选项数据失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@quality_router.get("/kline", response_model=ApiResponse)
async def check_kline_quality(
    symbol: str = Query(..., description="货币对，如BTCUSDT"),
    interval: str = Query(..., description="时间周期，如1m, 5m, 1h, 1d"),
    start: str | None = Query(None, description="开始时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    end: str | None = Query(None, description="结束时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    market_type: str = Query(
        "crypto",
        description="市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）",
    ),
    crypto_type: str = Query(
        "spot",
        description="加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）",
    ),
):
    """
    K线数据质量检查API

    用于检查Parquet文件中K线数据的质量，包括完整性、连续性、有效性和唯一性
    """
    try:
        from quality.kline_quality_service import KlineQualityService
        from quality.parquet_provider import ParquetDataProvider

        # 格式化 symbol 字段，去除其中的 "/" 字符
        formatted_symbol = symbol.replace("/", "")

        # 初始化服务
        provider = ParquetDataProvider()
        service = KlineQualityService(provider)

        # 执行质量检查
        result = service.check_quality(formatted_symbol, interval, crypto_type, start, end)

        return ApiResponse(code=0, message="获取K线数据质量报告成功", data=result)
    except Exception as e:
        logger.error(f"检查K线数据质量失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@quality_router.get("/kline/duplicates", response_model=ApiResponse)
async def get_kline_duplicates(
    symbol: str = Query(..., description="货币对，如BTCUSDT"),
    interval: str = Query(..., description="时间周期，如1m, 5m, 1h, 1d"),
    start: str | None = Query(None, description="开始时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    end: str | None = Query(None, description="结束时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    market_type: str = Query(
        "crypto",
        description="市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）",
    ),
    crypto_type: str = Query(
        "spot",
        description="加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）",
    ),
):
    """
    获取K线重复记录详情API

    用于获取K线数据中的重复记录详细信息，支持按时间范围查询
    """
    try:
        from quality.kline_quality_service import KlineQualityService
        from quality.parquet_provider import ParquetDataProvider

        formatted_symbol = symbol.replace("/", "")

        provider = ParquetDataProvider()
        service = KlineQualityService(provider)

        # 获取数据并检查唯一性
        df = provider.get_kline_data(formatted_symbol, interval, crypto_type, start, end)
        uniqueness_result = service.check_uniqueness(df)

        return ApiResponse(
            code=0,
            message="获取K线重复记录详情成功",
            data={
                "symbol": symbol,
                "interval": interval,
                "market_type": market_type,
                "crypto_type": crypto_type,
                "start_time": start,
                "end_time": end,
                "duplicate_records": uniqueness_result["duplicate_count"],
                "duplicate_details": uniqueness_result.get("duplicate_timestamps", []),
            },
        )
    except Exception as e:
        logger.error(f"获取K线重复记录详情失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@quality_router.post("/kline/duplicates/resolve", response_model=ApiResponse)
async def resolve_kline_duplicates(
    symbol: str = Query(..., description="货币对，如BTCUSDT"),
    interval: str = Query(..., description="时间周期，如1m, 5m, 1h, 1d"),
    strategy: str = Query(
        ...,
        description="处理策略：keep_first, keep_last, keep_max_volume, keep_min_volume",
    ),
    market_type: str = Query(
        "crypto",
        description="市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）",
    ),
    crypto_type: str = Query(
        "spot",
        description="加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）",
    ),
):
    """
    处理K线重复记录API

    用于处理K线数据中的重复记录，支持多种处理策略
    """
    # 验证处理策略
    valid_strategies = ["keep_first", "keep_last", "keep_max_volume", "keep_min_volume"]
    if strategy not in valid_strategies:
        raise HTTPException(
            status_code=400,
            detail=f"无效的处理策略: {strategy}，支持的策略：{', '.join(valid_strategies)}",
        )

    try:
        from quality.kline_quality_service import KlineQualityService
        from quality.parquet_provider import ParquetDataProvider

        formatted_symbol = symbol.replace("/", "")

        provider = ParquetDataProvider()
        service = KlineQualityService(provider)

        # 执行重复记录处理
        result = service.resolve_duplicates(
            symbol=formatted_symbol,
            interval=interval,
            candle_type=crypto_type,
            strategy=strategy,
        )

        return ApiResponse(
            code=0,
            message="重复记录处理成功",
            data={
                "symbol": symbol,
                "interval": interval,
                "strategy": strategy,
                "market_type": market_type,
                "crypto_type": crypto_type,
                **result,
            },
        )
    except Exception as e:
        logger.error(f"处理重复记录失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=f"处理重复记录失败: {e!s}")


# 将数据质量路由挂载到主路由下
router.include_router(quality_router)


# 数据清理路由
@router.post("/clean", response_model=ApiResponse)
async def clean_kline_data(
    symbol: str = Query(..., description="货币对，如BTCUSDT"),
    interval: str | None = Query(None, description="时间周期，如1m, 5m, 1h, 1d，为空时清理所有周期"),
    start: str | None = Query(None, description="开始时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    end: str | None = Query(None, description="结束时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    clean_type: str = Query(
        "all",
        description="清理类型：all(全部), duplicates(仅重复), invalid(仅无效数据)",
    ),
    market_type: str = Query(
        "crypto",
        description="市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）",
    ),
    crypto_type: str = Query(
        "spot",
        description="加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）",
    ),
    db: Session = Depends(get_db),
):
    """
    清理K线数据API

    用于清理数据库中的K线数据，支持按货币对、时间周期、时间范围清理
    支持清理重复数据、无效数据或全部清理

    Args:
        symbol: 货币对
        interval: 时间周期，为空时清理所有周期
        start: 开始时间
        end: 结束时间
        clean_type: 清理类型
        market_type: 市场类型
        crypto_type: 加密货币类型
        db: 数据库会话

    Returns:
        ApiResponse: 清理结果
    """
    # 格式化 symbol 字段，去除其中的 "/" 字符
    formatted_symbol = symbol.replace("/", "")

    # 解析时间参数
    start_dt = None
    end_dt = None

    if start:
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的开始时间格式: {start}")

    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的结束时间格式: {end}")

    # 根据市场类型和加密货币类型选择相应的模型
    KlineModel = None
    if market_type == "crypto":
        if crypto_type == "spot":
            KlineModel = CryptoSpotKline
        elif crypto_type == "future":
            KlineModel = CryptoFutureKline
        else:
            raise HTTPException(status_code=400, detail=f"不支持的加密货币类型: {crypto_type}")
    elif market_type == "stock":
        KlineModel = StockKline
    else:
        raise HTTPException(status_code=400, detail=f"不支持的市场类型: {market_type}")

    try:
        # 构建基础查询
        query = db.query(KlineModel).filter(KlineModel.symbol == formatted_symbol)

        # 添加时间周期过滤
        if interval:
            query = query.filter(KlineModel.interval == interval)

        # 添加时间范围过滤
        if start_dt:
            query = query.filter(KlineModel.timestamp >= start_dt)
        if end_dt:
            query = query.filter(KlineModel.timestamp <= end_dt)

        # 获取清理前的记录数
        total_before = query.count()

        deleted_count = 0

        if clean_type == "all":
            # 清理所有匹配的数据
            deleted_count = query.delete(synchronize_session=False)

        elif clean_type == "duplicates":
            # 仅清理重复数据
            # 获取数据
            checker = KlineHealthChecker()
            df = checker.get_kline_data(
                formatted_symbol,
                interval or "1m",
                start_dt,
                end_dt,
                market_type,
                crypto_type,
            )

            if not df.empty and "timestamp" in df.columns:
                # 找出重复的时间戳
                duplicate_timestamps = df[df.duplicated(subset=["timestamp"], keep=False)]["timestamp"].unique()

                # 删除重复记录（保留第一条）
                for ts in duplicate_timestamps:
                    # 获取该时间戳的所有记录
                    records = (
                        db.query(KlineModel)
                        .filter(
                            KlineModel.symbol == formatted_symbol,
                            KlineModel.timestamp == ts,
                        )
                        .all()
                    )

                    if len(records) > 1:
                        # 保留第一条，删除其他
                        for record in records[1:]:
                            db.delete(record)
                            deleted_count += 1

        elif clean_type == "invalid":
            # 仅清理无效数据
            # 获取数据
            checker = KlineHealthChecker()
            df = checker.get_kline_data(
                formatted_symbol,
                interval or "1m",
                start_dt,
                end_dt,
                market_type,
                crypto_type,
            )

            if not df.empty:
                # 找出无效记录
                invalid_indices = set()

                # 负价格
                negative_prices = df[(df["open"] < 0) | (df["high"] < 0) | (df["low"] < 0) | (df["close"] < 0)]
                invalid_indices.update(negative_prices.index.tolist())

                # 负成交量
                negative_volumes = df[df["volume"] < 0]
                invalid_indices.update(negative_volumes.index.tolist())

                # 高低价异常
                invalid_high_low = df[df["high"] < df["low"]]
                invalid_indices.update(invalid_high_low.index.tolist())

                # 删除无效记录
                for idx in invalid_indices:
                    if idx < len(df):
                        row = df.iloc[idx]
                        record = (
                            db.query(KlineModel)
                            .filter(
                                KlineModel.symbol == formatted_symbol,
                                KlineModel.timestamp == row["timestamp"],
                            )
                            .first()
                        )
                        if record:
                            db.delete(record)
                            deleted_count += 1

        # 提交事务
        db.commit()

        return ApiResponse(
            code=0,
            message="数据清理完成",
            data={
                "symbol": formatted_symbol,
                "interval": interval,
                "clean_type": clean_type,
                "start_time": start,
                "end_time": end,
                "total_before": total_before,
                "deleted_count": deleted_count,
                "market_type": market_type,
                "crypto_type": crypto_type,
            },
        )

    except Exception as e:
        db.rollback()
        logger.error(f"数据清理失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=f"数据清理失败: {e!s}")


@router.get("/features", response_model=ApiResponse)
def get_features(
    symbol: str | None = Query(None, description="货币名称"),
    db: Session = Depends(get_db),
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
                return ApiResponse(code=0, message=result["message"], data=result["feature_info"])
            else:
                return ApiResponse(code=0, message=result["message"], data=result["result"])
        else:
            return ApiResponse(code=1, message=result["message"], data={})
    except Exception as e:
        logger.error(f"获取特征失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features/{symbol}", response_model=ApiResponse)
def get_symbol_features(symbol: str, db: Session = Depends(get_db)):
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
            return ApiResponse(code=0, message=result["message"], data=result["feature_info"])
        else:
            return ApiResponse(code=1, message=result["message"], data={})
    except Exception as e:
        logger.error(f"获取货币特征失败: {e}")
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
            background_tasks.add_task(data_service.async_download_crypto, result["task_id"], request)

            return ApiResponse(
                code=0,
                message=result["message"],
                data={
                    "task_id": result["task_id"],
                    "message": "下载任务已创建，可通过 /api/data/task/{task_id} 查询进度",
                },
            )
        else:
            return ApiResponse(code=1, message=result["message"], data={})
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
            return ApiResponse(code=0, message=result["message"], data=result["task_info"])
        else:
            return ApiResponse(code=1, message=result["message"], data={"task_id": result["task_id"]})
    except Exception as e:
        logger.error(f"查询任务状态失败，任务ID: {task_id}, 错误: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export/crypto", response_model=ApiResponse)
def export_crypto(request: ExportCryptoRequest):
    """导出加密货币数据

    Args:
        request: 导出加密货币数据请求

    Returns:
        ApiResponse: 包含导出结果的响应
    """
    try:
        data_service = DataService()
        result = data_service.export_crypto_data(request)

        if result["success"]:
            return ApiResponse(code=0, message=result["message"], data=result["data"])
        else:
            return ApiResponse(code=1, message=result["message"], data={})
    except Exception as e:
        logger.error(f"导出加密货币数据失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crypto/symbols", response_model=ApiResponse)
def get_crypto_symbols(
    request: Request,
    exchange: str = Query(default="binance", description="交易所名称，如binance、okx等"),
    crypto_type: str | None = Query(default=None, description="加密货币类型，如spot（现货）、future（合约）等"),
    filter: str | None = Query(default=None, description="过滤条件，如'USDT'表示只返回USDT交易对"),
    limit: int | None = Query(default=100, description="返回数量限制"),
    offset: int | None = Query(default=0, description="返回偏移量"),
):
    """获取加密货币对列表

    Args:
        request: FastAPI请求对象，用于访问应用实例
        exchange: 交易所名称，如binance、okx等
        crypto_type: 加密货币类型，如spot（现货）、future（合约）等
        filter: 过滤条件，如'USDT'表示只返回USDT交易对
        limit: 返回数量限制
        offset: 返回偏移量

    Returns:
        ApiResponse: 包含货币对列表的响应
    """
    try:
        data_service = DataService()
        configs = request.app.state.configs
        result = data_service.get_crypto_symbols(exchange, filter, limit, offset, configs, crypto_type)

        if result["success"]:
            return ApiResponse(code=0, message=result["message"], data=result["response_data"])
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data={"error": result["error"], "exchange": result["exchange"]},
            )
    except Exception as e:
        logger.error(f"获取加密货币对列表失败: {e}")
        logger.exception(e)
        # 返回友好的错误信息给客户端
        return ApiResponse(
            code=1,
            message="获取加密货币对列表失败，请检查参数或稍后重试",
            data={"error": str(e), "exchange": exchange},
        )


@router.get("/tasks", response_model=ApiResponse)
def get_all_tasks(
    page: int = Query(1, ge=1, description="当前页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    task_type: str | None = Query(None, description="任务类型"),
    status: str | None = Query(None, description="任务状态"),
    start_time: str | None = Query(None, description="开始时间，格式YYYY-MM-DD HH:MM:SS"),
    end_time: str | None = Query(None, description="结束时间，格式YYYY-MM-DD HH:MM:SS"),
    created_at: str | None = Query(None, description="创建时间，格式YYYY-MM-DD HH:MM:SS"),
    updated_at: str | None = Query(None, description="更新时间，格式YYYY-MM-DD HH:MM:SS"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序顺序，asc或desc"),
    db: Session = Depends(get_db),
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
            sort_order=sort_order,
        )

        if result["success"]:
            return ApiResponse(code=0, message=result["message"], data=result["result"])
        else:
            return ApiResponse(code=1, message=result["message"], data={})
    except Exception as e:
        logger.error(f"查询任务列表失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/klines", response_model=ApiResponse)
def get_klines(
    symbol: str = Query(..., description="交易商标识"),
    interval: str = Query(..., description="时间周期，如5m、10m、1H、D等"),
    market_type: str = Query(
        "crypto",
        description="市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）",
    ),
    crypto_type: str | None = Query(
        "spot",
        description="加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）",
    ),
    start_time: str | None = Query(None, description="开始时间，格式YYYY-MM-DD HH:MM:SS"),
    end_time: str | None = Query(None, description="结束时间，格式YYYY-MM-DD HH:MM:SS"),
    limit: int | None = Query(5000, ge=1, le=10000, description="返回数据条数，默认5000条"),
    db: Session = Depends(get_db),
):
    """获取K线数据

    从数据库中查询指定交易对和周期的K线数据，支持不同市场类型

    Args:
        symbol: 交易商标识
        interval: 时间周期，如5m、10m、1H、D等
        market_type: 市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）
        crypto_type: 加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）
        start_time: 开始时间，格式YYYY-MM-DD HH:MM:SS
        end_time: 结束时间，格式YYYY-MM-DD HH:MM:SS
        limit: 返回数据条数，默认5000条
        db: 数据库会话

    Returns:
        ApiResponse: 包含K线数据的响应
    """
    try:
        # 验证市场类型参数
        valid_market_types = ["stock", "futures", "crypto"]
        if market_type not in valid_market_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的市场类型: {market_type}，可选值：{', '.join(valid_market_types)}",
            )

        # 验证加密货币类型参数
        if market_type == "crypto":
            valid_crypto_types = ["spot", "future"]
            if crypto_type not in valid_crypto_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的加密货币类型: {crypto_type}，可选值：{', '.join(valid_crypto_types)}",
                )

        data_service = DataService(db)
        result = data_service.get_kline_data(
            symbol=symbol,
            interval=interval,
            market_type=market_type,
            crypto_type=crypto_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        if result["success"]:
            return ApiResponse(code=0, message=result["message"], data=result["kline_data"])
        else:
            return ApiResponse(code=1, message=result["message"], data=[])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products", response_model=ApiResponse)
def get_products(
    market_type: str = Query(
        "crypto",
        description="市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）",
    ),
    crypto_type: str | None = Query(
        "spot",
        description="加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）",
    ),
    exchange: str | None = Query(None, description="交易商名称"),
    filter: str | None = Query(None, description="过滤条件"),
    limit: int | None = Query(100, ge=1, le=10000, description="返回数量限制，默认100条"),
    offset: int | None = Query(0, ge=0, description="返回偏移量，默认0"),
    db: Session = Depends(get_db),
):
    """获取商品列表

    根据市场类型和交易商获取商品列表数据

    Args:
        market_type: 市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）
        crypto_type: 加密货币类型，当market_type为crypto时有效，可选值：spot（现货）、future（合约）
        exchange: 交易商名称
        filter: 过滤条件
        limit: 返回数量限制，默认100条
        offset: 返回偏移量，默认0
        db: 数据库会话

    Returns:
        ApiResponse: 包含商品列表的响应
    """
    try:
        # 验证市场类型参数
        valid_market_types = ["stock", "futures", "crypto"]
        if market_type not in valid_market_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的市场类型: {market_type}，可选值：{', '.join(valid_market_types)}",
            )

        # 验证加密货币类型参数
        if market_type == "crypto":
            valid_crypto_types = ["spot", "future"]
            if crypto_type not in valid_crypto_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的加密货币类型: {crypto_type}，可选值：{', '.join(valid_crypto_types)}",
                )

        data_service = DataService(db)
        result = data_service.get_product_list(
            market_type=market_type,
            crypto_type=crypto_type,
            exchange=exchange,
            filter=filter,
            limit=limit,
            offset=offset,
        )

        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data={"products": result["products"], "total": result["total"]},
            )
        else:
            return ApiResponse(code=1, message=result["message"], data={"products": [], "total": 0})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取商品列表失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/details", response_model=ApiResponse)
def get_task_details(task_id: str = Path(..., description="任务ID"), db: Session = Depends(get_db)):
    """获取任务的子任务详情列表

    Args:
        task_id: 任务ID
        db: 数据库会话

    Returns:
        ApiResponse: 包含子任务详情列表的响应
    """
    try:
        from ..db.models import TaskDetailBusiness

        # 从数据库获取任务明细
        details = TaskDetailBusiness.get_by_task_id(task_id)

        # 转换为前端需要的格式
        task_details = [
            {
                "task_key": f"{d['interval']}:{d['symbol']}",
                "symbol": d["symbol"],
                "interval": d["interval"],
                "percentage": d["percentage"],
                "status": d["status_text"],
                "completed": d["completed"],
                "total": d["total"],
                "failed": d["failed"],
            }
            for d in details
        ]

        return ApiResponse(
            code=0,
            message="获取任务详情成功",
            data={
                "task_id": task_id,
                "details": task_details,
                "total": len(task_details),
            },
        )
    except Exception as e:
        logger.error(f"获取任务详情失败: task_id={task_id}, error={e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))
