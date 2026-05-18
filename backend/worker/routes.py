"""
Worker API路由定义

整合所有Worker相关的API端点
薄封装层：所有业务逻辑委托给 WorkerCoreService
"""

import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from . import schemas
from .core_service import (
    worker_core_service,
    WorkerNotFoundError,
    WorkerAlreadyRunningError,
    WorkerOperationError,
)
from .worker_state import worker_state_manager
from .dependencies import get_current_user
from collector.db.database import get_db as get_db_session
from utils.logger import get_logger, LogType
from worker.state import connection_manager, strategy_registry

logger = get_logger(__name__, LogType.APPLICATION)

router = APIRouter(
    prefix="/api/workers",
    tags=["workers"],
    responses={
        404: {"description": "Worker不存在"},
        500: {"description": "服务器内部错误"},
    },
)


# ==================== WebSocket端点 ====================

async def websocket_endpoint(websocket: WebSocket):
    await connection_manager.connect(websocket)
    await websocket.send_json({"type": "connection", "status": "connected"})

    last_snapshot_time = time.time()
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})

            now = time.time()
            if now - last_snapshot_time >= 3.0:
                strategies = [s.to_dict() for s in strategy_registry.list_all()]
                await websocket.send_json({
                    "type": "state_snapshot",
                    "strategies": strategies,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                last_snapshot_time = now
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)


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
        logger.error(f"创建Worker失败: {e}")
        import traceback
        traceback.print_exc()
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
    """
    获取Worker列表（支持分页、状态筛选和策略筛选）

    每个列表项包含简化的实时状态信息：
    - _status: 当前状态 (starting/running/stopping/stopped/error)
    - _pid: 进程ID
    - _updated_at: 状态最后更新时间

    性能优化：使用 get_all_states() 批量获取，避免 N+1 查询问题
    """
    try:
        result = await worker_core_service.async_list_workers(
            status=status, strategy_id=strategy_id, page=page, page_size=page_size
        )

        all_states = await worker_state_manager.get_all_states()
        items = result.get("items", [])

        for item in items:
            worker_id = item.get("id")
            if worker_id and worker_id in all_states:
                state = all_states[worker_id]
                item["_status"] = state.status
                item["_pid"] = state.pid
                item["_updated_at"] = state.updated_at.isoformat()
                # 优先使用实时状态覆盖数据库中的过时status值
                item["status"] = state.status

        return schemas.ApiResponse(code=0, message="success", data=result)
    except Exception as e:
        logger.error(f"获取Worker列表失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}", response_model=schemas.ApiResponse)
async def get_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    获取Worker详情（包含实时状态信息）

    返回内容：
    - 基础信息：来自数据库的 Worker 配置
    - _state_info：来自 state_manager 的实时状态详情
      * status: 当前状态 (starting/running/stopping/stopped/error)
      * previous_status: 前一状态
      * pid: 进程ID
      * started_at: 启动时间
      * stopped_at: 停止时间
      * error_message: 错误信息
      * updated_at: 状态最后更新时间
    """
    try:
        result = await worker_core_service.async_get_worker(worker_id)

        state = await worker_state_manager.get_state(worker_id)
        if state:
            result["_state_info"] = state.to_dict()

        return schemas.ApiResponse(code=0, message="success", data=result)
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 详情失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/state", response_model=schemas.ApiResponse)
async def get_worker_state(
    worker_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    获取Worker详细状态信息（专用端点）

    用于前端轮询或 WebSocket 推送，返回完整的 WorkerState 对象。

    返回内容：
    - worker_id: Worker ID
    - status: 当前状态 (starting/running/stopping/stopped/error)
    - previous_status: 前一状态
    - pid: 进程ID
    - started_at: 启动时间 (ISO 8601)
    - stopped_at: 停止时间 (ISO 8601)
    - error_message: 错误信息（如果有）
    - updated_at: 状态最后更新时间 (ISO 8601)

    性能特点：
    - 内存缓存查询，响应速度快
    - 适合高频轮询场景

    示例请求:
        GET /api/workers/10/state
    """
    try:
        state = await worker_state_manager.get_state(worker_id)

        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"Worker {worker_id} 状态信息不存在"
            )

        logger.debug(f"获取Worker {worker_id} 状态: {state.status}")

        return schemas.ApiResponse(
            code=0,
            message="success",
            data=state.to_dict()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 状态失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"更新Worker {worker_id} 失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"更新Worker {worker_id} 配置失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"删除Worker {worker_id} 失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"克隆Worker {worker_id} 失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"批量操作Worker失败: {e}")
        import traceback
        traceback.print_exc()
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
    启动Worker（异步操作）

    业务逻辑委托给 WorkerCoreService，状态管理由 WorkerStateManager 负责。

    返回内容：
    - status: "starting" 表示已接收启动请求
    - message: 提示信息说明这是异步操作
    - _state_info: 当前状态快照（可选）

    错误处理：
    - 404: Worker 不存在
    - 409: 非法状态转换（如重复启动）
    - 400: 其他业务错误
    - 500: 内部服务器错误

    注意：此操作为异步执行，实际状态变更请通过 GET /workers/{worker_id}/state 轮询
    """
    try:
        state = await worker_state_manager.get_state(worker_id)

        if state and state.status in ("running", "starting"):
            raise HTTPException(
                status_code=409,
                detail=f"Worker {worker_id} 当前状态为 {state.status}，不允许再次启动。请先停止 Worker。"
            )

        result = await worker_core_service.async_start_worker(worker_id)

        current_state = await worker_state_manager.get_state(worker_id)
        response_data = {
            "worker_id": worker_id,
            "status": "starting",
            "message": "Worker 启动请求已接收，正在异步处理中。请通过 GET /workers/{worker_id}/state 查询最新状态。",
        }
        if current_state:
            response_data["_state_snapshot"] = {
                "status": current_state.status,
                "updated_at": current_state.updated_at.isoformat(),
            }
        result.update(response_data)

        logger.info(f"Worker {worker_id} 启动请求已接收")

        return schemas.ApiResponse(code=0, message="Worker启动中（异步操作）", data=result)
    except HTTPException:
        raise
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerAlreadyRunningError:
        state = await worker_state_manager.get_state(worker_id)
        current_status = state.status if state else "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"Worker {worker_id} 当前状态为 {current_status}，不允许再次启动。请先停止 Worker。"
        )
    except WorkerOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"启动Worker {worker_id} 失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动Worker失败: {str(e)}")


@router.post("/{worker_id}/lifecycle/stop", response_model=schemas.ApiResponse)
async def stop_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    停止Worker（异步操作）

    业务逻辑委托给 WorkerCoreService，状态管理由 WorkerStateManager 负责。

    返回内容：
    - status: "stopping" 表示已接收停止请求
    - message: 提示信息说明这是异步操作
    - _state_info: 当前状态快照（可选）

    错误处理：
    - 404: Worker 不存在
    - 409: 非法状态转换（如重复停止）
    - 400: 其他业务错误
    - 500: 内部服务器错误

    注意：此操作为异步执行，实际状态变更请通过 GET /workers/{worker_id}/state 轮询
    """
    try:
        state = await worker_state_manager.get_state(worker_id)

        if state and state.status in ("stopped", "stopping"):
            raise HTTPException(
                status_code=409,
                detail=f"Worker {worker_id} 当前状态为 {state.status}，不允许再次停止。"
            )

        result = await worker_core_service.async_stop_worker(worker_id)

        current_state = await worker_state_manager.get_state(worker_id)
        response_data = {
            "worker_id": worker_id,
            "status": "stopping",
            "message": "Worker 停止请求已接收，正在异步处理中。请通过 GET /workers/{worker_id}/state 查询最新状态。",
        }
        if current_state:
            response_data["_state_snapshot"] = {
                "status": current_state.status,
                "updated_at": current_state.updated_at.isoformat(),
            }
        result.update(response_data)

        logger.info(f"Worker {worker_id} 停止请求已接收")

        return schemas.ApiResponse(code=0, message="Worker停止中（异步操作）", data=result)
    except HTTPException:
        raise
    except WorkerNotFoundError:
        raise HTTPException(status_code=404, detail="Worker不存在")
    except WorkerOperationError as e:
        error_msg = str(e)
        if "已停止" in error_msg or "not running" in error_msg.lower():
            return schemas.ApiResponse(
                code=0,
                message="Worker已处于停止状态",
                data={"worker_id": worker_id, "status": "stopped"}
            )
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        logger.error(f"停止Worker {worker_id} 失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"重启Worker {worker_id} 失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"获取Worker {worker_id} 状态失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"Worker {worker_id} 健康检查失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"获取Worker {worker_id} 性能指标失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"获取Worker {worker_id} 历史指标失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"获取Worker {worker_id} 日志失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"清理Worker {worker_id} 日志失败: {e}")
        import traceback
        traceback.print_exc()
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
    from .dependencies import get_current_user
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
    from . import service

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
        logger.error(f"获取Worker {worker_id} 绩效统计失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"获取Worker {worker_id} 交易记录失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略代理模块 ====================

@router.get("/{worker_id}/strategy/parameters", response_model=schemas.ApiResponse)
async def get_strategy_parameters(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取策略参数 - 委托给 crud 层"""
    from . import crud

    try:
        params = crud.get_worker_parameters(db, worker_id)
        return schemas.ApiResponse(code=0, message="success", data=[p.to_dict() for p in params])
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 策略参数失败: {e}")
        import traceback
        traceback.print_exc()
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

    更新数据库中的策略参数
    """
    from . import crud

    try:
        crud.update_worker_parameters(db, worker_id, request.parameters)
        return schemas.ApiResponse(code=0, message="参数更新成功")
    except Exception as e:
        logger.error(f"更新Worker {worker_id} 策略参数失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/strategy/positions", response_model=schemas.ApiResponse)
async def get_positions(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取持仓信息 - 委托给 service 层"""
    from . import service

    try:
        positions = await service.get_positions(worker_id)
        return schemas.ApiResponse(code=0, message="success", data=positions)
    except Exception as e:
        logger.error(f"获取Worker {worker_id} 持仓信息失败: {e}")
        import traceback
        traceback.print_exc()
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
        logger.error(f"获取Worker {worker_id} 订单信息失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ========== 兼容性函数（供 main.py 和 core/lifespan.py 使用）==========

async def shutdown_worker_manager():
    """
    关闭 WorkerManager（兼容性接口）

    直接使用 WorkerSystem 全局单例进行关闭操作
    确保与 lifespan.py 中的初始化/关闭逻辑一致
    """
    try:
        logger.info("[routes] 正在关闭 WorkerManager...")

        from .worker_system import worker_system

        if not worker_system._initialized:
            logger.info("[routes] NautilusTradingSystem 未初始化，跳过关闭")
            return

        # 停止所有运行中的 Worker（通过 NautilusTradingSystem）
        strategies = worker_system.list_strategies()
        stopped_count = 0
        for s in strategies:
            if s["status"] in ("running", "starting"):
                try:
                    await worker_system.stop_strategy(s["worker_id"])
                    stopped_count += 1
                    logger.info(f"[routes] 已停止 Worker {s['worker_id']}")
                except Exception as e:
                    logger.warning(f"[routes] 停止 Worker {s['worker_id']} 失败: {e}")

        logger.info(f"[routes] 已停止 {stopped_count} 个运行中的 Worker")
        logger.info("[routes] WorkerManager 关闭完成")

    except Exception as e:
        logger.error(f"[routes] 关闭 WorkerManager 失败: {e}")


# ==================== 实时日志模块 ====================

@router.get("/{worker_id}/logs/recent", response_model=schemas.ApiResponse)
async def get_worker_recent_logs(
    worker_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="最大返回条数"),
    level: Optional[str] = Query(
        default=None,
        pattern=r"^(DEBUG|INFO|WARNING|ERROR)$",
        description="日志级别过滤"
    ),
    keyword: Optional[str] = Query(default=None, description="关键词搜索（不区分大小写）"),
):
    """
    获取 Worker 最近日志（从内存缓冲区实时查询）

    适用场景：
    - 实时查看 Worker 运行状态
    - 快速定位错误日志
    - 开发调试
    - 监控告警

    示例请求:
        GET /api/workers/001/logs/recent?limit=50&level=ERROR&keyword=timeout
    """
    try:
        from .log_utils import get_global_buffer

        buffer = get_global_buffer()
        logs = buffer.get_recent(
            limit=limit,
            level=level,
            worker_id=worker_id,
            keyword=keyword,
        )

        return schemas.ApiResponse(
            code=0,
            message=f"获取成功，共 {len(logs)} 条日志",
            data={
                "worker_id": worker_id,
                "count": len(logs),
                "logs": logs,
                "query_time": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"[routes] 获取 Worker {worker_id} 日志失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询日志失败: {str(e)}")


@router.get("/logs/stats", response_model=schemas.ApiResponse)
async def get_global_log_stats():
    """
    获取全局日志统计信息

    返回：
    - 缓冲区使用率
    - 各级别日志分布
    - 总追加/淘汰数量
    """
    try:
        from .log_utils import get_global_buffer

        buffer = get_global_buffer()
        stats = buffer.get_stats()

        return schemas.ApiResponse(
            code=0,
            message="获取统计信息成功",
            data=stats
        )

    except Exception as e:
        logger.error(f"[routes] 获取日志统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/search", response_model=schemas.ApiResponse)
async def search_logs(
    query: str = Query(..., description="搜索关键词", min_length=1),
    limit: int = Query(default=100, ge=1, le=500, description="最大返回条数"),
):
    """
    全文搜索日志

    在所有日志消息、logger名称、Worker ID 中搜索匹配的条目
    """
    try:
        from .log_utils import get_global_buffer

        buffer = get_global_buffer()
        results = buffer.search(query=query, limit=limit)

        return schemas.ApiResponse(
            code=0,
            message=f"搜索完成，找到 {len(results)} 条匹配",
            data={
                "query": query,
                "count": len(results),
                "results": results,
            }
        )

    except Exception as e:
        logger.error(f"[routes] 搜索日志失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
