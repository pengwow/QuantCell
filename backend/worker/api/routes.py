"""
Worker API路由定义

整合所有Worker相关的API端点
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, WebSocket
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from .. import schemas, crud, service
from ..dependencies import get_db, get_current_user
from collector.db.database import get_db as get_db_session

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
    """
    创建新的Worker节点
    
    - 验证Worker名称唯一性
    - 创建数据库记录
    - 初始化Worker配置
    """
    try:
        worker = crud.create_worker(db, request)
        return schemas.ApiResponse(
            code=0,
            message="Worker创建成功",
            data=worker.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    获取Worker列表
    
    支持分页、状态筛选和策略筛选
    """
    try:
        workers, total = crud.get_workers(
            db, 
            status=status, 
            strategy_id=strategy_id,
            skip=(page - 1) * page_size,
            limit=page_size
        )
        return schemas.ApiResponse(
            code=0,
            message="success",
            data={
                "items": [w.to_dict() for w in workers],
                "total": total,
                "page": page,
                "page_size": page_size
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}", response_model=schemas.ApiResponse)
async def get_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker详情"""
    worker = crud.get_worker(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker不存在")
    return schemas.ApiResponse(
        code=0,
        message="success",
        data=worker.to_dict()
    )


@router.put("/{worker_id}", response_model=schemas.ApiResponse)
async def update_worker(
    worker_id: int,
    request: schemas.WorkerUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """更新Worker配置"""
    worker = crud.update_worker(db, worker_id, request)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker不存在")
    return schemas.ApiResponse(
        code=0,
        message="Worker更新成功",
        data=worker.to_dict()
    )


@router.patch("/{worker_id}/config", response_model=schemas.ApiResponse)
async def update_worker_config(
    worker_id: int,
    request: schemas.WorkerConfigUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """部分更新Worker配置"""
    worker = crud.update_worker_config(db, worker_id, request.config)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker不存在")
    return schemas.ApiResponse(
        code=0,
        message="配置更新成功",
        data=worker.to_dict()
    )


@router.delete("/{worker_id}", response_model=schemas.ApiResponse)
async def delete_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """删除Worker"""
    success = crud.delete_worker(db, worker_id)
    if not success:
        raise HTTPException(status_code=404, detail="Worker不存在")
    return schemas.ApiResponse(
        code=0,
        message="Worker删除成功"
    )


@router.post("/{worker_id}/clone", response_model=schemas.ApiResponse)
async def clone_worker(
    worker_id: int,
    request: schemas.WorkerCloneRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """克隆Worker"""
    try:
        new_worker = crud.clone_worker(db, worker_id, request)
        return schemas.ApiResponse(
            code=0,
            message="Worker克隆成功",
            data=new_worker.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch", response_model=schemas.ApiResponse)
async def batch_operation(
    request: schemas.BatchOperationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    批量操作Worker
    
    支持批量启动、停止、重启
    """
    try:
        result = await service.batch_operation(db, request)
        return schemas.ApiResponse(
            code=0,
            message="批量操作完成",
            data=result
        )
    except Exception as e:
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
    启动Worker
    
    异步启动Worker进程，通过ZeroMQ发送启动命令
    """
    try:
        worker = crud.get_worker(db, worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker不存在")
        
        # 异步启动Worker
        task_id = await service.start_worker_async(worker_id)
        return schemas.ApiResponse(
            code=0,
            message="Worker启动中",
            data={"task_id": task_id, "status": "starting"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/lifecycle/stop", response_model=schemas.ApiResponse)
async def stop_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    停止Worker
    
    通过ZeroMQ发送停止命令
    """
    try:
        worker = crud.get_worker(db, worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker不存在")
        
        success = await service.stop_worker(worker_id)
        if success:
            return schemas.ApiResponse(
                code=0,
                message="Worker停止成功"
            )
        else:
            raise HTTPException(status_code=500, detail="Worker停止失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/lifecycle/restart", response_model=schemas.ApiResponse)
async def restart_worker(
    worker_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """重启Worker"""
    try:
        worker = crud.get_worker(db, worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker不存在")
        
        task_id = await service.restart_worker_async(worker_id)
        return schemas.ApiResponse(
            code=0,
            message="Worker重启中",
            data={"task_id": task_id, "status": "restarting"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/lifecycle/pause", response_model=schemas.ApiResponse)
async def pause_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """暂停Worker"""
    try:
        success = await service.pause_worker(worker_id)
        if success:
            return schemas.ApiResponse(
                code=0,
                message="Worker已暂停"
            )
        else:
            raise HTTPException(status_code=500, detail="暂停失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/lifecycle/resume", response_model=schemas.ApiResponse)
async def resume_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """恢复Worker"""
    try:
        success = await service.resume_worker(worker_id)
        if success:
            return schemas.ApiResponse(
                code=0,
                message="Worker已恢复"
            )
        else:
            raise HTTPException(status_code=500, detail="恢复失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/lifecycle/status", response_model=schemas.ApiResponse)
async def get_worker_status(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker实时状态"""
    try:
        status = await service.get_worker_status(worker_id)
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=status
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/lifecycle/health", response_model=schemas.ApiResponse)
async def health_check(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """Worker健康检查"""
    try:
        health = await service.health_check(worker_id)
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=health
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 监控数据模块 ====================

@router.get("/{worker_id}/monitoring/metrics", response_model=schemas.ApiResponse)
async def get_worker_metrics(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    获取Worker实时性能指标
    
    包括CPU使用率、内存占用、网络I/O等
    """
    try:
        metrics = await service.get_worker_metrics(worker_id)
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=metrics
        )
    except Exception as e:
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
    """获取历史性能指标"""
    try:
        history = crud.get_metrics_history(
            db, worker_id, start_time, end_time, interval
        )
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=history
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/monitoring/logs", response_model=schemas.ApiResponse)
async def get_worker_logs(
    worker_id: int,
    level: Optional[str] = Query(None, description="日志级别筛选"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取Worker日志"""
    try:
        logs = crud.get_worker_logs(
            db, worker_id, level, start_time, end_time, limit
        )
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=[log.to_dict() for log in logs]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/{worker_id}/monitoring/logs/stream")
async def log_stream(websocket: WebSocket, worker_id: int):
    """
    WebSocket实时日志流
    
    通过WebSocket实时推送Worker日志
    """
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
    """获取Worker绩效统计"""
    try:
        performance = crud.get_worker_performance(db, worker_id, days)
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=[p.to_dict() for p in performance]
        )
    except Exception as e:
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
    """获取Worker交易记录"""
    try:
        trades, total = crud.get_worker_trades(
            db, worker_id, symbol, start_time, end_time, 
            skip=(page - 1) * page_size, limit=page_size
        )
        return schemas.ApiResponse(
            code=0,
            message="success",
            data={
                "items": [t.to_dict() for t in trades],
                "total": total,
                "page": page,
                "page_size": page_size
            }
        )
    except Exception as e:
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
    
    通过ZeroMQ发送策略部署命令
    """
    try:
        result = await service.deploy_strategy(worker_id, request)
        return schemas.ApiResponse(
            code=0,
            message="策略部署成功",
            data=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/strategy/undeploy", response_model=schemas.ApiResponse)
async def undeploy_strategy(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """卸载Worker上的策略"""
    try:
        result = await service.undeploy_strategy(worker_id)
        return schemas.ApiResponse(
            code=0,
            message="策略卸载成功",
            data=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/strategy/parameters", response_model=schemas.ApiResponse)
async def get_strategy_parameters(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取策略参数"""
    try:
        params = crud.get_worker_parameters(db, worker_id)
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=[p.to_dict() for p in params]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{worker_id}/strategy/parameters", response_model=schemas.ApiResponse)
async def update_strategy_parameters(
    worker_id: int,
    request: schemas.StrategyParameterUpdate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """更新策略参数"""
    try:
        # 更新数据库
        crud.update_worker_parameters(db, worker_id, request.parameters)
        
        # 通过ZeroMQ通知Worker更新参数
        await service.update_strategy_params(worker_id, request.parameters)
        
        return schemas.ApiResponse(
            code=0,
            message="参数更新成功"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/strategy/positions", response_model=schemas.ApiResponse)
async def get_positions(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取持仓信息"""
    try:
        positions = await service.get_positions(worker_id)
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=positions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}/strategy/orders", response_model=schemas.ApiResponse)
async def get_orders(
    worker_id: int,
    status: Optional[str] = Query(None, description="订单状态筛选"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """获取订单信息"""
    try:
        orders = await service.get_orders(worker_id, status)
        return schemas.ApiResponse(
            code=0,
            message="success",
            data=orders
        )
    except Exception as e:
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
    
    通过ZeroMQ发送交易信号到Worker
    """
    try:
        result = await service.send_trading_signal(worker_id, signal)
        return schemas.ApiResponse(
            code=0,
            message="信号发送成功",
            data=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
