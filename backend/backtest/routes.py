"""
回测模块API路由

提供回测相关的RESTful API端点。

路由前缀: /api/backtest
标签: backtest

包含端点:
    - GET /list: 获取回测列表
    - POST /run: 执行回测
    - POST /stop: 终止回测
    - GET /{backtest_id}: 获取回测详情
    - GET /{backtest_id}/replay: 获取回测回放数据
    - GET /{backtest_id}/symbols: 获取回测货币对列表
    - POST /analyze: 分析回测结果
    - DELETE /delete/{backtest_id}: 删除回测结果
    - POST /check-data: 检查数据完整性
    - POST /download-data: 下载缺失数据

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from strategy.schemas import StrategyUploadRequest
from utils.auth import get_current_user
from utils.logger import LogType, get_logger
from utils.rbac import is_guest_user

from .data_provider import BacktestDataProvider
from .progress_tracker import StageStatus, get_progress_tracker
from .schemas import (
    ApiResponse,
    BacktestAnalyzeRequest,
    BacktestListRequest,
    BacktestProgressResponse,
    BacktestRunRequest,
    BacktestStopRequest,
    DataDownloadResponse,
    DataIntegrityCheckRequest,
    DataIntegrityCheckResponse,
    StrategyConfigRequest,
)
from .service import BacktestService

# 获取模块日志器（import 全部完成后定义）
logger = get_logger(__name__, LogType.APPLICATION)

# 创建回测服务实例
backtest_service = BacktestService()

# 创建API路由实例
router = APIRouter(
    prefix="/api/v1/backtest",
    tags=["backtest"],
    responses={
        200: {"description": "成功响应", "model": ApiResponse},
        500: {"description": "内部服务器错误"},
    },
)


@router.get(
    "/list",
    response_model=ApiResponse,
    summary="获取回测列表",
    description="获取所有回测任务的列表，支持分页查询",
    responses={
        200: {"description": "获取回测列表成功"},
        500: {"description": "获取回测列表失败"},
    },
)
def get_backtest_list(request: BacktestListRequest | None = None) -> ApiResponse:
    """
    获取所有回测结果列表

    Args:
        request: 回测列表请求参数，包含分页信息，可选

    Returns:
        ApiResponse: API响应，包含回测结果列表
    """
    try:
        logger.info("获取回测结果列表请求")

        # 获取回测结果列表（使用正确的 API 方法名）
        backtests = backtest_service.get_result_list()

        logger.info(f"成功获取回测结果列表，共 {len(backtests)} 个回测结果")

        return ApiResponse(code=0, message="获取回测结果列表成功", data={"backtests": backtests})
    except Exception as e:
        logger.error(f"获取回测结果列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/strategies",
    response_model=ApiResponse,
    summary="获取策略类型列表",
    description="获取所有支持的策略类型列表",
)
def get_strategy_list() -> ApiResponse:
    """
    获取所有支持的策略类型列表

    Returns:
        ApiResponse: API响应，包含策略类型列表
    """
    try:
        logger.info("获取策略类型列表请求")

        # 直接返回空列表，保持原有接口，但实际不再使用
        strategies = []

        logger.info("成功获取策略类型列表")

        return ApiResponse(code=0, message="获取策略类型列表成功", data={"strategies": strategies})
    except Exception as e:
        logger.error(f"获取策略类型列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/precheck-data",
    response_model=ApiResponse,
    summary="回测前数据预检",
    description="检查给定品种×周期的 Parquet 文件是否存在，返回缺失列表。只读文件系统，不加载数据。",
)
def precheck_data(
    symbols: str,
    timeframes: str,
    candle_type: str = "spot",
) -> ApiResponse:
    """回测前预检哪些品种缺少本地数据。

    Args:
        symbols: 逗号分隔的交易对列表，如 "ETH/USDT,LTC/USDT"
        timeframes: 逗号分隔的周期列表，如 "15m,1h"
        candle_type: 市场类型 spot/future

    Returns:
        ApiResponse: data 包含 all_available / missing / available
    """
    try:
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
        timeframe_list = [t.strip() for t in timeframes.split(",") if t.strip()]

        if not symbol_list or not timeframe_list:
            return ApiResponse(
                code=0,
                message="参数为空，无需检查",
                data={"all_available": True, "missing": [], "available": []},
            )

        provider = BacktestDataProvider()
        result = provider.check_data_availability(
            symbols=symbol_list,
            timeframes=timeframe_list,
            candle_type=candle_type,
        )

        return ApiResponse(code=0, message="数据预检完成", data=result)
    except Exception as e:
        logger.error(f"数据预检失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/run",
    response_model=ApiResponse,
    summary="执行回测",
    description="根据策略配置和回测配置创建回测任务，异步执行并立即返回任务ID",
    responses={
        200: {"description": "回测任务创建成功"},
        500: {"description": "回测任务创建失败"},
    },
)
def run_backtest(request: BacktestRunRequest) -> ApiResponse:
    """
    创建回测任务并异步执行

    创建回测任务后立即返回任务ID，后端在后台线程中异步执行回测。
    前端可以通过 /api/backtest/progress/{task_id} 接口轮询获取进度。

    Args:
        request: 回测执行请求参数，包含策略配置和回测配置

    Returns:
        ApiResponse: API响应，包含任务ID和初始状态
    """
    import json
    import threading
    import uuid
    from datetime import datetime

    from backtest.models import BacktestTask
    from utils.db_session import get_db_session
    from utils.validation import parse_time_range, validate_time_range

    try:
        logger.info("=" * 80)
        logger.info("收到回测任务请求")
        logger.info(f"策略名称: {request.strategy_config.strategy_name}")
        logger.info(f"策略参数: {json.dumps(request.strategy_config.params, ensure_ascii=False)}")
        logger.info(f"回测引擎: {request.backtest_config.engine_type}")
        logger.info(f"交易对: {request.backtest_config.symbols}")
        logger.info(f"时间周期: {request.backtest_config.interval}")
        logger.info(f"初始资金: {request.backtest_config.initial_cash}")
        logger.info(f"时间范围: {request.backtest_config.start_time} 至 {request.backtest_config.end_time}")
        logger.info("=" * 80)

        # 处理时间范围格式（支持YYYYMMDD-YYYYMMDD格式）
        backtest_config_dict = request.backtest_config.model_dump()
        strategy_config_dict = request.strategy_config.model_dump()

        # 检查并转换时间范围格式
        start_time = backtest_config_dict.get("start_time")
        backtest_config_dict.get("end_time")

        # 如果是YYYYMMDD-YYYYMMDD格式，解析并转换
        if start_time and "-" in start_time and len(start_time) == 17:
            try:
                if validate_time_range(start_time):
                    start_dt, end_dt = parse_time_range(start_time)
                    backtest_config_dict["start_time"] = start_dt.strftime("%Y-%m-%d 00:00:00")
                    backtest_config_dict["end_time"] = end_dt.strftime("%Y-%m-%d 23:59:59")
                    logger.info(
                        f"时间范围格式转换: {start_time} -> {backtest_config_dict['start_time']} 至 {backtest_config_dict['end_time']}"
                    )
            except Exception as e:
                logger.warning(f"时间范围格式转换失败，使用原值: {e}")

        # 生成任务ID
        task_id = str(uuid.uuid4())
        logger.info(f"生成任务ID: {task_id}")

        with get_db_session() as db:
            # 创建回测任务记录
            task = BacktestTask(
                id=task_id,
                strategy_name=request.strategy_config.strategy_name,
                backtest_config=json.dumps(backtest_config_dict, default=str, ensure_ascii=False),
                status="pending",
                started_at=datetime.now(UTC),
            )
            db.add(task)
            db.commit()

            logger.info(f"回测任务记录已保存到数据库: {task_id}")

            # 创建进度记录
            progress_tracker = get_progress_tracker()
            progress_tracker.create_progress(task_id)
            progress_tracker.update_progress(task_id, "overall", {"status": "running"})

            # 在后台线程中异步执行回测
            def run_backtest_async():
                try:
                    logger.info(f"[任务 {task_id}] 开始后台执行回测")
                    logger.info(f"[任务 {task_id}] 使用引擎: {backtest_config_dict.get('engine_type', 'default')}")

                    # 先通过 BacktestService 创建任务（保存到文件系统）
                    service_task_id = backtest_service.create_task(
                        strategy_name=strategy_config_dict.get("strategy_name", ""),
                        strategy_params=strategy_config_dict.get("params", {}),
                        symbols=backtest_config_dict.get("symbols", []),
                        timeframes=[backtest_config_dict.get("interval", "1h")],
                        engine_type=backtest_config_dict.get("engine_type", "default"),
                        config=backtest_config_dict,
                        task_id=task_id,  # 使用原始的 UUID 作为 task_id
                    )
                    logger.info(f"[任务 {task_id}] BacktestService 任务已创建: {service_task_id}")

                    # 执行回测
                    result = backtest_service.run_backtest(task_id=service_task_id, progress_tracker=progress_tracker)

                    logger.info(f"[任务 {task_id}] 回测执行完成，状态: {result.get('status')}")
                    # 回测成功状态可能是 'success' 或 'completed'
                    if result.get("status") in ("success", "completed"):
                        logger.info(f"[任务 {task_id}] 回测成功完成: {result.get('message')}")
                        # 如果有失败的货币对，记录警告日志
                        failed_currencies = result.get("failed_currencies", [])
                        if failed_currencies:
                            logger.warning(f"[任务 {task_id}] 部分货币对回测失败: {failed_currencies}")
                    else:
                        # 增强失败日志，显示更多详细信息
                        failed_currencies = result.get("failed_currencies", [])
                        successful_currencies = result.get("successful_currencies", [])
                        error_details = result.get("results", {}).get("errors", [])
                        logger.error(
                            f"[任务 {task_id}] 回测失败: {result.get('message')}, "
                            f"成功: {len(successful_currencies)}个, "
                            f"失败: {len(failed_currencies)}个, "
                            f"失败货币对: {failed_currencies}, "
                            f"错误详情: {error_details}"
                        )
                except Exception as e:
                    logger.error(f"[任务 {task_id}] 回测执行发生异常: {e}")
                    logger.exception(e)
                    # 更新进度为失败状态
                    progress_tracker.fail_progress(task_id, f"回测执行失败: {e!s}", "execution")

            # 启动后台线程
            thread = threading.Thread(target=run_backtest_async, daemon=True)
            thread.start()

            logger.info(f"回测任务 {task_id} 已在后台线程启动")

            # 立即返回任务ID
            return ApiResponse(
                code=0,
                message="回测任务已创建",
                data={
                    "task_id": task_id,
                    "status": "pending",
                    "message": "回测任务已创建并开始执行，请通过进度接口查询状态",
                },
            )

    except Exception as e:
        logger.error(f"创建回测任务失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/stop",
    response_model=ApiResponse,
    summary="终止回测",
    description="终止正在进行的回测任务",
    responses={
        200: {"description": "回测终止成功"},
        404: {"description": "回测任务不存在"},
        500: {"description": "终止回测失败"},
    },
)
def stop_backtest(request: BacktestStopRequest) -> ApiResponse:
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
            return ApiResponse(code=0, message="回测已终止", data=result)
        else:
            return ApiResponse(code=1, message=result.get("message", "终止回测失败"), data=result)
    except Exception as e:
        logger.error(f"终止回测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/analyze",
    response_model=ApiResponse,
    summary="分析回测结果",
    description="分析回测结果并返回详细分析数据",
)
def analyze_backtest(request: BacktestAnalyzeRequest) -> ApiResponse:
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

        # 与 stop 端点一致：按 service 返回的 status 区分成败，error 时 message 透传原因
        if result.get("status") == "success":
            return ApiResponse(code=0, message="回测结果分析成功", data=result)
        return ApiResponse(code=1, message=result.get("message", "回测结果分析失败"), data=result)
    except Exception as e:
        logger.error(f"回测结果分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/delete",
    response_model=ApiResponse,
    summary="删除回测结果（无ID）",
    description="删除回测结果（未提供ID时返回重定向提示）",
)
def delete_backtest_no_id(request: Request, current_user: dict = Depends(get_current_user)) -> JSONResponse:
    """
    删除回测结果（无ID时返回重定向）

    Returns:
        JSONResponse: 重定向响应
    """
    return JSONResponse(
        status_code=307,
        content={
            "code": -1,
            "message": "请提供回测ID",
            "data": {"redirect": "/api/v1/backtest/list"},
        },
    )


@router.delete(
    "/delete/{backtest_id}",
    response_model=ApiResponse,
    summary="删除回测结果",
    description="删除指定ID的回测结果",
)
def delete_backtest(request: Request, backtest_id: str, current_user: dict = Depends(get_current_user)) -> ApiResponse:
    """
    删除回测结果

    Args:
        backtest_id: 回测ID

    Returns:
        ApiResponse: API响应，包含回测删除结果
    """
    try:
        logger.info(f"删除回测结果请求，回测ID: {backtest_id}")

        # 检查是否为访客用户
        if is_guest_user(request):
            logger.warning(f"访客用户尝试删除回测结果，回测ID: {backtest_id}")
            raise HTTPException(
                status_code=403,
                detail={
                    "code": 403,
                    "message": "访客用户无法删除回测记录，请使用普通用户账号登录",
                    "data": {"is_guest": True},
                },
            )

        # 删除回测结果
        result = backtest_service.delete_backtest_result(backtest_id)

        if result:
            logger.info(f"回测结果删除成功，回测ID: {backtest_id}")
            return ApiResponse(
                code=0,
                message="回测结果删除成功",
                data={"backtest_id": backtest_id, "result": result},
            )
        else:
            logger.warning(f"回测结果删除失败，回测ID: {backtest_id}")
            return ApiResponse(
                code=1,
                message="回测结果删除失败",
                data={"backtest_id": backtest_id, "result": result},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回测结果删除失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/strategy/config",
    response_model=ApiResponse,
    summary="创建策略配置",
    description="创建策略配置并返回配置信息",
)
def create_strategy_config(request: StrategyConfigRequest) -> ApiResponse:
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
            "params": request.params,
        }

        logger.info(f"策略配置创建成功，策略名称: {request.strategy_name}")
        return ApiResponse(
            code=0,
            message="策略配置创建成功",
            data={"strategy_config": strategy_config},
        )
    except Exception as e:
        logger.error(f"策略配置创建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/strategy",
    response_model=ApiResponse,
    summary="上传策略文件",
    description="上传策略文件到系统",
)
def upload_strategy(request: StrategyUploadRequest) -> ApiResponse:
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
            strategy_name=request.strategy_name, file_content=request.file_content
        )

        if result:
            logger.info(f"策略文件上传成功，策略名称: {request.strategy_name}")
            return ApiResponse(
                code=0,
                message="策略文件上传成功",
                data={"strategy_name": request.strategy_name},
            )
        else:
            logger.error(f"策略文件上传失败，策略名称: {request.strategy_name}")
            return ApiResponse(code=1, message="策略文件上传失败", data={})
    except Exception as e:
        logger.error(f"策略文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{backtest_id}",
    response_model=ApiResponse,
    summary="获取回测详情",
    description="获取指定回测ID的详细结果，多品种回测可通过 symbol 参数切换品种",
)
def get_backtest_detail(backtest_id: str, symbol: str | None = None) -> ApiResponse:
    """
    获取回测结果详情

    任务信息与策略代码从数据库读取；结果数据仅来自结果 JSON 文件
    （文件不存在时相关字段返回空列表）。多品种回测通过 symbol 指定品种；
    传 "all" 或缺省时返回组合视图（组合指标 + 各品种交易/持仓拼接 +
    按时间戳对齐求和的组合权益曲线）。

    Args:
        backtest_id: 回测ID
        symbol: 品种（如 "ETH/USDT"），或 "all" 查看组合视图；缺省同 "all"（多品种）

    Returns:
        ApiResponse: API响应，包含回测结果详情
    """
    try:
        logger.info(f"获取回测结果详情请求，回测ID: {backtest_id}")

        # models/db_session 在函数内 import：依赖数据库连接初始化时机，保持原有加载模式
        from backtest.models import BacktestTask
        from strategy.models import Strategy
        from utils.db_session import get_db_session

        with get_db_session() as db:
            task = db.query(BacktestTask).filter_by(id=backtest_id).first()

            if not task:
                logger.error(f"回测任务不存在，回测ID: {backtest_id}")
                return ApiResponse(code=1, message="回测任务不存在", data={})

            # 解析回测配置
            backtest_config = {}
            try:
                if task.backtest_config:
                    backtest_config = json.loads(task.backtest_config)
            except Exception as e:
                logger.warning(f"解析回测配置失败: {e}")

            # 获取策略代码（Strategy 模型的代码字段是 code，不是 content）
            strategy_code = None
            try:
                strategy = db.query(Strategy).filter_by(name=task.strategy_name).first()
                if strategy:
                    strategy_code = strategy.code
            except Exception as e:
                logger.warning(f"获取策略代码失败: {e}")

            status = task.status
            metrics: list = []
            trades: list = []
            equity_curve: list = []
            positions: list = []
            factors: dict = {}

            # 结果 JSON 是回测结果的唯一真实来源；无 JSON（未跑完/已清理）时保持空列表
            json_result = backtest_service.get_result(backtest_id)
            result_symbols: list[str] = []
            if isinstance(json_result, dict):
                status = json_result.get("status") or status
                results = json_result.get("results") or {}
                # 归一化单品种 / 多品种(results_by_symbol)两种结构
                entries = backtest_service.extract_symbol_entries(results)
                result_symbols = list(entries.keys())

                # 多品种组合视图：symbol=all，或多品种缺省（未指定具体品种）
                is_multi = len(result_symbols) > 1
                use_portfolio = is_multi and (symbol == "all" or symbol is None)
                if use_portfolio:
                    view = backtest_service.build_portfolio_view(results)
                    metrics = view["metrics"]
                    trades = view["trades"]
                    equity_curve = view["equity_curve"]
                    positions = view["positions"]
                    factors = {}
                else:
                    # 指定品种优先，缺省（单品种）取第一个品种
                    entry = entries.get(symbol) if symbol else None
                    if entry is None and symbol:
                        logger.warning(f"结果中未找到品种 {symbol}，回退到第一个品种")
                    if entry is None:
                        entry = next(iter(entries.values()), {})

                    metrics = entry.get("metrics") or []
                    trades = entry.get("trades") or []
                    equity_curve = entry.get("equity_curve") or []
                    positions = entry.get("positions") or []
                    factors = entry.get("factors") or {}

            # 构建前端期望的响应格式
            detail_data = {
                "id": task.id,
                "strategy_name": task.strategy_name,
                "backtest_config": backtest_config,
                "metrics": metrics,
                "equity_curve": equity_curve,
                "trades": trades,
                "positions": positions,
                "factors": factors,
                # 结果中实际有数据的品种列表（多品种切换用），及当前返回的品种
                "symbols": result_symbols,
                "selected_symbol": (
                    "all"
                    if isinstance(json_result, dict) and len(result_symbols) > 1 and (symbol == "all" or symbol is None)
                    else (symbol if symbol in result_symbols else (result_symbols[0] if result_symbols else None))
                ),
                "is_multi_symbol": len(result_symbols) > 1,
                "status": status,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "code": strategy_code,
            }

            logger.info(f"成功获取回测结果详情，回测ID: {backtest_id}")
            return ApiResponse(code=0, message="获取回测结果详情成功", data=detail_data)

    except Exception as e:
        logger.error(f"获取回测结果详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{backtest_id}/replay",
    response_model=ApiResponse,
    summary="获取回测回放数据",
    description="获取回放所需的 K 线、成交记录与权益曲线（取自结果 JSON 文件），支持按品种过滤",
)
def get_backtest_replay(backtest_id: str, symbol: str | None = None) -> ApiResponse:
    """
    获取回测回放数据（供前端回放页 klinecharts 渲染）

    Args:
        backtest_id: 回测ID
        symbol: 品种（如 "ETH/USDT"），缺省取结果中的第一个品种

    Returns:
        ApiResponse: API响应，包含 kline_data/trades/equity_curve/backtest_config 等
    """
    try:
        logger.info(f"获取回放数据请求，回测ID: {backtest_id}, 品种: {symbol}")

        # 任务信息走数据库（结果 JSON 里只有结果数据）
        from backtest.models import BacktestTask
        from utils.db_session import get_db_session

        json_result = backtest_service.get_result(backtest_id)
        if not isinstance(json_result, dict):
            return ApiResponse(code=1, message="回测结果文件不存在", data={})

        results = json_result.get("results") or {}

        # 归一化单品种（键 "ETH/USDT_15m"）/ 多品种（results_by_symbol 封装）结构
        entries = backtest_service.extract_symbol_entries(results)
        entry = entries.get(symbol) if symbol else None
        if entry is None and symbol:
            logger.warning(f"结果中未找到品种 {symbol}，回退到第一个品种")
        if entry is None:
            entry = next(iter(entries.values()), {})
        entry = entry if isinstance(entry, dict) else {}

        backtest_config = {}
        created_at = None
        strategy_name = ""
        task_status = ""
        with get_db_session() as db:
            task = db.query(BacktestTask).filter_by(id=backtest_id).first()
            if task:
                strategy_name = task.strategy_name
                created_at = task.created_at.isoformat() if task.created_at else None
                task_status = task.status
                try:
                    if task.backtest_config:
                        backtest_config = json.loads(task.backtest_config)
                except Exception as e:
                    logger.warning(f"解析回测配置失败: {e}")

        # backtest_config中的 symbol/interval 以结果实际品种为准（回放页据此初始化图表）
        if entry.get("symbol"):
            backtest_config["symbol"] = entry["symbol"]
        if entry.get("timeframe"):
            backtest_config["interval"] = entry["timeframe"]

        replay_data = {
            "id": backtest_id,
            "strategy_name": strategy_name,
            "backtest_config": backtest_config,
            "metrics": entry.get("metrics") or [],
            "kline_data": entry.get("klines") or [],
            "trades": entry.get("trades") or [],
            "equity_curve": entry.get("equity_curve") or [],
            "factors": entry.get("factors") or {},
            "status": json_result.get("status") or task_status,
            "created_at": created_at,
            "metadata": {
                "successful_currencies": json_result.get("successful_currencies", []),
                "failed_currencies": json_result.get("failed_currencies", []),
            },
        }

        logger.info(f"成功获取回放数据，回测ID: {backtest_id}")
        return ApiResponse(code=0, message="获取回放数据成功", data=replay_data)

    except Exception as e:
        logger.error(f"获取回放数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{backtest_id}/replay/portfolio",
    response_model=ApiResponse,
    summary="获取全局视角回测回放时间轴",
    description="多品种回测的全局回放：统一时间网格 + 组合账户序列 + 成交流重建的持仓事件 + 持仓期收盘价点",
)
def get_backtest_replay_portfolio(backtest_id: str) -> ApiResponse:
    """
    获取全局视角回测回放数据（组合时间机器）

    与单品种 /replay 接口的区别：时钟是覆盖全部品种的统一时间网格，账户数字
    为各独立资金池合并口径，持仓由跨品种成交流重建。

    Args:
        backtest_id: 回测ID

    Returns:
        ApiResponse: 包含 start_ms/end_ms/grid_count/grid_step_ms/account/
                     position_events/holding_prices/trades
    """
    try:
        logger.info(f"获取全局回放数据请求，回测ID: {backtest_id}")

        # models/db_session 在函数内 import：依赖数据库连接初始化时机，保持原有加载模式
        from backtest.models import BacktestTask
        from utils.db_session import get_db_session

        json_result = backtest_service.get_result(backtest_id)
        if not isinstance(json_result, dict):
            return ApiResponse(code=1, message="回测结果文件不存在", data={})

        results = json_result.get("results") or {}
        entries = backtest_service.extract_symbol_entries(results)
        if len(entries) <= 1:
            return ApiResponse(code=1, message="该回测不是多品种回测，无全局视角", data={})

        backtest_config: dict = {}
        with get_db_session() as db:
            task = db.query(BacktestTask).filter_by(id=backtest_id).first()
            if task:
                try:
                    if task.backtest_config:
                        backtest_config = json.loads(task.backtest_config)
                except Exception as e:
                    logger.warning(f"解析回测配置失败: {e}")

        data = backtest_service.build_portfolio_replay(results, backtest_config)
        logger.info(
            f"全局回放数据构建成功，回测ID: {backtest_id}, "
            f"网格点数: {data['grid_count']}, 持仓事件: {len(data['position_events'])}"
        )
        return ApiResponse(code=0, message="获取全局回放数据成功", data=data)

    except Exception as e:
        logger.error(f"获取全局回放数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{backtest_id}/symbols",
    response_model=ApiResponse,
    summary="获取回测货币对列表",
    description="获取回测包含的所有货币对信息，用于多货币对切换展示",
)
def get_backtest_symbols(backtest_id: str) -> ApiResponse:
    """
    获取回测包含的所有货币对信息

    Args:
        backtest_id: 回测ID

    Returns:
        ApiResponse: API响应，包含回测货币对列表
    """
    try:
        logger.info(f"获取回测货币对列表请求，回测ID: {backtest_id}")

        # 获取回测货币对列表
        result = backtest_service.get_backtest_symbols(backtest_id)

        if result and result.get("status") == "success":
            logger.info(f"成功获取回测货币对列表，回测ID: {backtest_id}")
            return ApiResponse(code=0, message="获取回测货币对列表成功", data=result.get("data"))
        else:
            logger.error(f"获取回测货币对列表失败，回测ID: {backtest_id}")
            return ApiResponse(code=1, message="获取回测货币对列表失败", data={})
    except Exception as e:
        logger.error(f"获取回测货币对列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/check-data",
    response_model=DataIntegrityCheckResponse,
    summary="检查回测数据完整性",
    description="检查指定交易对在指定时间范围内的数据完整性",
)
def check_data_integrity(
    request: DataIntegrityCheckRequest,
) -> DataIntegrityCheckResponse:
    """
    检查回测数据完整性

    Args:
        request: 数据完整性检查请求参数

    Returns:
        DataIntegrityCheckResponse: 检查结果
    """
    try:
        logger.info(f"数据完整性检查请求: {request.symbol} {request.interval}")

        # 解析时间
        start_time = datetime.strptime(request.start_time, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(request.end_time, "%Y-%m-%d %H:%M:%S")

        # 执行检查
        from .data_integrity import DataIntegrityChecker

        checker = DataIntegrityChecker()
        result = checker.check_data_completeness(
            symbol=request.symbol,
            interval=request.interval,
            start_time=start_time,
            end_time=end_time,
            market_type=request.market_type,
            crypto_type=request.crypto_type,
        )

        # 转换结果为响应格式
        response_data = {
            "is_complete": result.is_complete,
            "total_expected": result.total_expected,
            "total_actual": result.total_actual,
            "missing_count": result.missing_count,
            "missing_ranges": [
                {"start": start.isoformat(), "end": end.isoformat()} for start, end in result.missing_ranges
            ],
            "quality_issues": result.quality_issues,
            "coverage_percent": round(result.coverage_percent, 2),
        }

        logger.info(f"数据完整性检查完成: {request.symbol}, 覆盖率: {result.coverage_percent:.2f}%")

        return DataIntegrityCheckResponse(code=0, message="数据完整性检查完成", data=response_data)
    except Exception as e:
        logger.error(f"数据完整性检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/download-data",
    response_model=DataDownloadResponse,
    summary="下载缺失的回测数据",
    description="下载指定交易对在指定时间范围内的缺失数据",
)
def download_missing_data(request: DataIntegrityCheckRequest) -> DataDownloadResponse:
    """
    下载缺失的回测数据

    Args:
        request: 数据下载请求参数

    Returns:
        DataDownloadResponse: 下载进度信息
    """
    try:
        logger.info(f"数据下载请求: {request.symbol} {request.interval}")

        # 解析时间
        start_time = datetime.strptime(request.start_time, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(request.end_time, "%Y-%m-%d %H:%M:%S")

        # 创建下载器
        from .data_downloader import BacktestDataDownloader

        downloader = BacktestDataDownloader()

        # 执行下载（同步方式，会等待下载完成）
        success, _result = downloader.ensure_data_complete(
            symbol=request.symbol,
            interval=request.interval,
            start_time=start_time,
            end_time=end_time,
            market_type=request.market_type,
            crypto_type=request.crypto_type,
            max_wait_time=300,  # 最多等待5分钟
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
            "error": None if success else "下载失败或超时",
        }

        logger.info(f"数据下载完成: {request.symbol}, 成功: {success}")

        return DataDownloadResponse(
            code=0 if success else 1,
            message="数据下载完成" if success else "数据下载失败",
            data=response_data,
        )
    except Exception as e:
        logger.error(f"数据下载失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/progress/{task_id}",
    response_model=BacktestProgressResponse,
    summary="获取回测任务进度",
    description="获取指定回测任务的实时进度信息",
    responses={
        200: {"description": "获取进度成功"},
        404: {"description": "任务不存在"},
        500: {"description": "获取进度失败"},
    },
)
def get_backtest_progress(task_id: str) -> BacktestProgressResponse:
    """
    获取回测任务进度

    Args:
        task_id: 回测任务ID

    Returns:
        BacktestProgressResponse: 回测进度数据
    """
    try:
        logger.debug(f"获取回测任务进度: {task_id}")

        # 获取进度跟踪器
        tracker = get_progress_tracker()
        progress = tracker.get_progress(task_id)

        if not progress:
            return BacktestProgressResponse(code=1, message=f"任务不存在: {task_id}", data=None)

        # 转换为响应格式
        response_data = {
            "task_id": progress.task_id,
            "status": progress.status.value if isinstance(progress.status, StageStatus) else progress.status,
            "current_stage": progress.current_stage.value
            if hasattr(progress.current_stage, "value")
            else progress.current_stage,
            "overall_progress": progress.overall_progress,
            "data_prep": {
                "status": progress.data_prep.status.value
                if isinstance(progress.data_prep.status, StageStatus)
                else progress.data_prep.status,
                "progress": progress.data_prep.progress,
                "current_step": progress.data_prep.current_step.value
                if hasattr(progress.data_prep.current_step, "value")
                else progress.data_prep.current_step,
                "checked_symbols": progress.data_prep.checked_symbols,
                "total_symbols": progress.data_prep.total_symbols,
                "downloading": progress.data_prep.downloading,
                "message": progress.data_prep.message,
            },
            "execution": {
                "status": progress.execution.status.value
                if isinstance(progress.execution.status, StageStatus)
                else progress.execution.status,
                "progress": progress.execution.progress,
                "current_symbol": progress.execution.current_symbol,
                "completed_symbols": progress.execution.completed_symbols,
                "total_symbols": progress.execution.total_symbols,
                "message": progress.execution.message,
            },
            "analysis": {
                "status": progress.analysis.status.value
                if isinstance(progress.analysis.status, StageStatus)
                else progress.analysis.status,
                "progress": progress.analysis.progress,
                "message": progress.analysis.message,
            },
            "error": {"stage": progress.error.stage, "message": progress.error.message} if progress.error else None,
            "created_at": progress.created_at,
            "updated_at": progress.updated_at,
        }

        return BacktestProgressResponse(code=0, message="获取进度成功", data=response_data)

    except Exception as e:
        logger.error(f"获取回测任务进度失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
