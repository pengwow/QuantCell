"""
Worker API路由定义

整合所有Worker相关的API端点
薄封装层：所有业务逻辑委托给 WorkerCoreService
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, WebSocket, Request
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime

from .. import schemas
from ..core_service import (
    worker_core_service,
    WorkerNotFoundError,
    WorkerAlreadyRunningError,
    WorkerOperationError,
)
from ..dependencies import get_current_user
from collector.db.database import get_db as get_db_session
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(
    prefix="/api/workers",
    tags=["workers"],
    responses={
        404: {"description": "Worker不存在"},
        500: {"description": "服务器内部错误"},
    },
)


# ==================== 基础管理模块 ====================

@router.post("", response_model=schemas.ApiResponse)
async def create_worker(
    request: schemas.WorkerCreate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """创建新的Worker节点 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_create_worker(request.dict())
        return schemas.ApiResponse(code=0, message="Worker创建成功", data=result)
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建Worker失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=schemas.ApiResponse)
async def list_workers(
    status: Optional[str] = Query(None, description="按状态筛选"),
    strategy_id: Optional[int] = Query(None, description="按策略ID筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker列表（支持分页、状态筛选和策略筛选）- 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_list_workers(
            status=status, strategy_id=strategy_id, page=page, page_size=page_size
        )
        return schemas.ApiResponse(code=0, message="success", data=result)
    except Exception as e:
        logger.error(f"获取Worker列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}", response_model=schemas.ApiResponse)
async def get_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker详情 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_get_worker(worker_id)
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{worker_id}", response_model=schemas.ApiResponse)
async def update_worker(
    worker_id: int,
    request: schemas.WorkerUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """更新Worker配置 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_update_worker(
            worker_id, request.dict(exclude_unset=True)
        )
        return schemas.ApiResponse(code=0, message="Worker更新成功", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{worker_id}/config", response_model=schemas.ApiResponse)
async def update_worker_config(
    worker_id: int,
    request: schemas.WorkerConfigUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """部分更新Worker配置 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_update_worker_config(worker_id, request.config)
        return schemas.ApiResponse(code=0, message="配置更新成功", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新Worker {worker_id} 配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{worker_id}", response_model=schemas.ApiResponse)
async def delete_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """删除Worker - 委托给 WorkerCoreService"""
    try:
        await worker_core_service.async_delete_worker(worker_id)
        return schemas.ApiResponse(code=0, message="Worker删除成功")
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/clone", response_model=schemas.ApiResponse)
async def clone_worker(
    worker_id: int,
    request: schemas.WorkerCloneRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """克隆Worker - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_clone_worker(
            worker_id, request.new_name, request.copy_config, request.copy_parameters
        )
        return schemas.ApiResponse(code=0, message="Worker克隆成功", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="源Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"克隆Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=schemas.ApiResponse)
async def batch_operation(
    request: schemas.BatchOperationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """批量操作Worker（支持批量启动、停止、重启）- 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_batch_operation(
            request.worker_ids, request.operation
        )
        return schemas.ApiResponse(code=0, message="批量操作完成", data=result)
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"批量操作Worker失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 生命周期管理模块 ====================

@router.post("/{worker_id}/lifecycle/start", response_model=schemas.ApiResponse)
async def start_worker(
    worker_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    启动Worker - 委托给 WorkerCoreService
    
    从原来的280+行简化到30行以内
    所有业务逻辑（策略加载、配置准备、进程管理）都在 core_service 中处理
    """
    try:
        result = await worker_core_service.async_start_worker(worker_id)
        return schemas.ApiResponse(code=0, message="Worker启动成功", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerAlreadyRunningError as e:
        return schemas.ApiResponse(
            code=0, message=str(e), data={"worker_id": worker_id, "status": "running"}
        )
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"启动Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动Worker失败: {str(e)}")


@router.post("/{worker_id}/lifecycle/stop", response_model=schemas.ApiResponse)
async def stop_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """停止Worker - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_stop_worker(worker_id)
        if result.get("message") == "Worker 已停止":
            return schemas.ApiResponse(
                code=0, message="Worker已处于停止状态",
                data={"worker_id": worker_id, "status": "stopped"}
            )
        return schemas.ApiResponse(code=0, message="Worker停止成功", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"停止Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"停止Worker失败: {str(e)}")


@router.post("/{worker_id}/lifecycle/restart", response_model=schemas.ApiResponse)
async def restart_worker(
    worker_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """重启Worker - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_restart_worker(worker_id)
        return schemas.ApiResponse(code=0, message="Worker重启中", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"重启Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/lifecycle/status", response_model=schemas.ApiResponse)
async def get_worker_status(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker实时状态 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_get_worker_status(worker_id)
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/lifecycle/health", response_model=schemas.ApiResponse)
async def health_check(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Worker健康检查 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_health_check(worker_id)
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except Exception as e:
        logger.error(f"Worker {worker_id} 健康检查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 监控数据模块 ====================

@router.get("/{worker_id}/monitoring/metrics", response_model=schemas.ApiResponse)
async def get_worker_metrics(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker实时性能指标 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_get_worker_metrics(worker_id)
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 性能指标失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/monitoring/metrics/history", response_model=schemas.ApiResponse)
async def get_metrics_history(
    worker_id: int,
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    interval: str = Query("1m", description="时间间隔: 1m, 5m, 1h"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取历史性能指标 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_get_metrics_history(
            worker_id, start_time, end_time, interval
        )
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 历史指标失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/monitoring/logs", response_model=schemas.ApiResponse)
async def get_worker_logs(
    worker_id: int,
    level: Optional[str] = Query(None, description="日志级别筛选 (DEBUG/INFO/WARNING/ERROR)"),
    start_time: Optional[datetime] = Query(None, description="开始时间 (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="结束时间 (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数 (1-1000)"),
    offset: int = Query(0, ge=0, description="偏移量（用于分页）"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    获取 Worker 日志（基于文件系统 - 高性能方案）
    
    直接从日志文件读取，支持分页查询，无数据库压力 - 委托给 WorkerCoreService
    """
    try:
        result = await worker_core_service.async_get_worker_logs(
            worker_id, level, start_time, end_time, limit, offset
        )
        return schemas.ApiResponse(code=0, message="success", data=result)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} 的日志文件不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 日志失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{worker_id}/monitoring/logs", response_model=schemas.ApiResponse)
async def clear_worker_logs(
    worker_id: int,
    before_days: Optional[int] = Query(None, description="清理多少天前的日志，不指定则清理所有"),
    confirm: bool = Query(False, description="确认清空操作（安全措施）"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    清理 Worker 日志文件
    
    安全措施：需要确认参数，记录操作审计日志 - 委托给 WorkerCoreService
    """
    try:
        result = await worker_core_service.async_clear_worker_logs(
            worker_id, before_days, confirm
        )
        logger.info(
            f"用户 {current_user.get('username')} 清理了 Worker {worker_id} 的日志文件, "
            f"删除 {result.get('deleted_count', 0)} 个文件"
        )
        return schemas.ApiResponse(code=0, message=f"成功清理 {result.get('deleted_count', 0)} 个日志文件", data=result)
    except ValueError as e:
        return schemas.ApiResponse(code=400, message=str(e), data=None)
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"清理Worker {worker_id} 日志失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/monitoring/logs/stream")
async def log_stream_sse(
    worker_id: int,
    request: Request,
    token: Optional[str] = Query(None, description="JWT token for SSE authentication (EventSource cannot send headers)")
):
    """
    SSE 实时日志流 (推荐方案)

    通过 Server-Sent Events 实时推送 Worker 日志。
    
    特殊路由：保留较多代码因为涉及 EventSourceResponse 和流式生成器
    但日志读取逻辑委托给 core_service 的 _get_log_file_reader 方法
    """
    from ..dependencies import get_current_user
    from fastapi.responses import EventSourceResponse
    from fastapi.sse import format_sse_event, KEEPALIVE_COMMENT
    import json as json_module

    current_user = await get_current_user(request, token=token)

    reader = worker_core_service._get_log_file_reader(str(worker_id))

    async def event_generator():
        logger.info(f"Worker {worker_id} SSE 日志流: 开始生成事件流")
        try:
            history_logs = reader.tail_logs(str(worker_id), lines=100)
            logger.info(f"SSE 日志流: tail_logs 返回 {len(history_logs)} 条历史日志")
            for idx, log_entry in enumerate(history_logs):
                if await request.is_disconnected():
                    logger.info(f"SSE 日志流: 客户端已断开 (history #{idx})")
                    break
                yield format_sse_event(
                    data_str=json_module.dumps(log_entry, ensure_ascii=False),
                    event="history",
                    id=f"history-{idx}",
                )

            if await request.is_disconnected():
                return

            logger.info(f"SSE 日志流: 发送 history_complete 信号")
            yield format_sse_event(event="history_complete", data_str='{"status": "complete"}')

            event_id = 1000
            logger.info(f"SSE 日志流: 开始监控实时日志 (poll_interval=0.2s)")
            async for new_log in reader.watch_logs(
                worker_id=str(worker_id),
                poll_interval=0.2,
            ):
                if await request.is_disconnected():
                    logger.info(f"SSE 日志流: 客户端已断开 (log #{event_id})")
                    break

                event_id += 1
                yield format_sse_event(
                    data_str=json_module.dumps(new_log, ensure_ascii=False),
                    event="log",
                    id=str(event_id),
                )
        except Exception as e:
            import traceback
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['close', 'disconnect', 'cancelled']):
                logger.info(f"Worker {worker_id} SSE 日志流: 客户端断开连接")
            else:
                logger.error(f"SSE 日志流异常: {e}\n{traceback.format_exc()}")
            yield format_sse_event(event="error", data_str=json_module.dumps({"error": str(e)}))

    return EventSourceResponse(event_generator())


@router.websocket("/{worker_id}/monitoring/logs/stream/ws")
async def log_stream(websocket: WebSocket, worker_id: int):
    """
    WebSocket实时日志流 (降级方案)

    仅用于不支持 SSE 的旧浏览器或特殊场景。
    新代码推荐使用 SSE 端点：GET /api/workers/{worker_id}/monitoring/logs/stream
    """
    from .. import service

    await websocket.accept()
    try:
        await service.stream_logs(websocket, worker_id)
    except Exception as e:
        await websocket.close(code=1011, reason=str(e))


@router.get("/{worker_id}/monitoring/performance", response_model=schemas.ApiResponse)
async def get_worker_performance(
    worker_id: int,
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker绩效统计 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_get_worker_performance(worker_id, days)
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 绩效统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/monitoring/trades", response_model=schemas.ApiResponse)
async def get_worker_trades(
    worker_id: int,
    symbol: Optional[str] = Query(None, description="交易对筛选"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker交易记录 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_get_worker_trades(
            worker_id, symbol, page, page_size
        )
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 交易记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略代理模块 ====================

@router.post("/{worker_id}/strategy/deploy", response_model=schemas.ApiResponse)
async def deploy_strategy(
    worker_id: int,
    request: schemas.StrategyDeployRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    部署策略到Worker
    
    通过ZeroMQ发送策略部署命令 - 委托给 service 层
    """
    from .. import service

    try:
        result = await service.deploy_strategy(worker_id, request)
        return schemas.ApiResponse(code=0, message="策略部署成功", data=result)
    except Exception as e:
        logger.error(f"部署策略到Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/strategy/undeploy", response_model=schemas.ApiResponse)
async def undeploy_strategy(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """卸载Worker上的策略 - 委托给 service 层"""
    from .. import service

    try:
        result = await service.undeploy_strategy(worker_id)
        return schemas.ApiResponse(code=0, message="策略卸载成功", data=result)
    except Exception as e:
        logger.error(f"卸载Worker {worker_id} 策略失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/strategy/parameters", response_model=schemas.ApiResponse)
async def get_strategy_parameters(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取策略参数 - 委托给 crud 层"""
    from .. import crud

    try:
        params = crud.get_worker_parameters(db, worker_id)
        return schemas.ApiResponse(code=0, message="success", data=[p.to_dict() for p in params])
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 策略参数失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{worker_id}/strategy/parameters", response_model=schemas.ApiResponse)
async def update_strategy_parameters(
    worker_id: int,
    request: schemas.StrategyParameterUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    更新策略参数
    
    更新数据库并通过ZeroMQ通知Worker更新参数 - 委托给 crud 和 service 层
    """
    from .. import crud, service

    try:
        crud.update_worker_parameters(db, worker_id, request.parameters)
        await service.update_strategy_params(worker_id, request.parameters)
        return schemas.ApiResponse(code=0, message="参数更新成功")
    except Exception as e:
        logger.error(f"更新Worker {worker_id} 策略参数失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/strategy/positions", response_model=schemas.ApiResponse)
async def get_positions(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取持仓信息 - 委托给 service 层"""
    from .. import service

    try:
        positions = await service.get_positions(worker_id)
        return schemas.ApiResponse(code=0, message="success", data=positions)
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 持仓信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/strategy/orders", response_model=schemas.ApiResponse)
async def get_orders(
    worker_id: int,
    status: Optional[str] = Query(None, description="订单状态筛选"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取订单信息 - 委托给 WorkerCoreService"""
    try:
        result = await worker_core_service.async_get_worker_orders(worker_id, status)
        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 订单信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/strategy/signal", response_model=schemas.ApiResponse)
async def send_trading_signal(
    worker_id: int,
    signal: Dict[str, Any],
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    发送交易信号
    
    通过ZeroMQ发送交易信号到Worker - 委托给 service 层
    """
    from .. import service

    try:
        result = await service.send_trading_signal(worker_id, signal)
        return schemas.ApiResponse(code=0, message="信号发送成功", data=result)
    except Exception as e:
        logger.error(f"发送交易信号到Worker {worker_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========== 兼容性函数（供 main.py 和 core/lifespan.py 使用）==========

async def shutdown_worker_manager():
    """
    关闭 WorkerManager（兼容性接口）
    
    薄封装：委托给 WorkerCoreService 处理
    保留此函数以确保与 main.py 和 core/lifespan.py 的向后兼容
    """
    try:
        logger.info("[routes] 正在关闭 WorkerManager...")
        # 停止所有运行中的 Worker
        result = worker_core_service.list_workers(status='running')
        running_workers = result.get('items', [])
        
        if running_workers:
            for worker in running_workers:
                worker_id = worker.get('id')
                try:
                    await worker_core_service.async_stop_worker(worker_id)
                    logger.info(f"[routes] 已停止 Worker {worker_id}")
                except Exception as e:
                    logger.warning(f"[routes] 停止 Worker {worker_id} 失败: {e}")
        
        # 清理 WorkerManager 实例
        if worker_core_service._worker_manager is not None:
            try:
                await worker_core_service._worker_manager.stop()
                logger.info("[routes] WorkerManager 已停止")
            except Exception as e:
                logger.warning(f"[routes] 停止 WorkerManager 时出错: {e}")
            
            worker_core_service._worker_manager = None
        
        logger.info("[routes] WorkerManager 关闭完成")
        
    except Exception as e:
        logger.error(f"[routes] 关闭 WorkerManager 失败: {e}", exc_info=True)
