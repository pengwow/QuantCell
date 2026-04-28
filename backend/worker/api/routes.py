"""
Worker API路由定义

整合所有Worker相关的API端点
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, WebSocket
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime

from .. import schemas, crud, service
from ..dependencies import get_current_user
from collector.db.database import get_db as get_db_session
from utils.logger import get_logger, LogType

# 获取模块日志器
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

# 全局 WorkerManager 实例（单例模式）
_worker_manager = None

def _on_worker_exit(worker_id: str, worker_status):
    """
    Worker 退出回调函数
    
    当 Worker 进程异常退出时，更新数据库状态
    """
    try:
        # 创建数据库会话
        from collector.db.database import SessionLocal
        db = SessionLocal()
        try:
            # 获取 Worker 记录
            from .. import crud
            worker = crud.get_worker(db, int(worker_id))
            if worker and worker.status == "running":
                # 更新状态为 stopped
                worker.status = "stopped"
                worker.pid = None
                worker.started_at = None
                worker.stopped_at = datetime.now()
                db.commit()
                logger.info(f"Worker {worker_id} 异常退出，数据库状态已更新为 stopped")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Worker 退出回调处理失败: {e}")

async def get_worker_manager():
    """获取 WorkerManager 实例（懒加载）"""
    global _worker_manager
    if _worker_manager is None:
        from ..manager import WorkerManager
        _worker_manager = WorkerManager()
        # 注册 Worker 退出回调
        _worker_manager.register_worker_exit_callback(_on_worker_exit)
        # 启动 WorkerManager
        await _worker_manager.start()
        logger.info("WorkerManager 初始化并启动完成，已注册退出回调")
    return _worker_manager


@router.post("/{worker_id}/lifecycle/start", response_model=schemas.ApiResponse)
async def start_worker(
    worker_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    启动Worker
    
    创建并启动Worker进程，通过ZeroMQ进行进程间通信
    """
    try:
        worker = crud.get_worker(db, worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker不存在")
        
        # 检查 Worker 是否已在运行
        if worker.status == "running":
            return schemas.ApiResponse(
                code=0,
                message="Worker已在运行中",
                data={"worker_id": worker_id, "status": "running"}
            )
        
        # 获取 WorkerManager 实例
        manager = await get_worker_manager()
        
        # 获取策略信息（优先使用数据库中的 code 字段）
        strategy_path = None
        strategy_code = None
        if worker.strategy_id:
            # 从策略表中获取策略信息
            from strategy.models import Strategy
            strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()
            if strategy:
                # 优先使用数据库中的 code 字段
                if strategy.code:
                    strategy_code = strategy.code
                    logger.info(f"使用数据库策略代码 (策略: {strategy.name}, ID: {strategy.id})")
                # 如果没有 code，尝试使用 file_name 构建路径
                elif strategy.file_name:
                    strategy_path = f"strategies/{strategy.file_name}"
                    logger.info(f"使用策略路径: {strategy_path} (策略: {strategy.name})")
                else:
                    # 回退：使用策略ID作为文件名
                    strategy_path = f"strategies/{worker.strategy_id}.py"
                    logger.warning(f"策略代码和文件均未找到，使用默认路径: {strategy_path}")
            else:
                # 回退：使用策略ID作为文件名
                strategy_path = f"strategies/{worker.strategy_id}.py"
                logger.warning(f"策略未找到，使用默认路径: {strategy_path}")

        # 记录实际使用的策略路径
        if strategy_path:
            logger.info(f"Worker {worker_id} 使用策略路径: {strategy_path}")
        if strategy_code:
            logger.info(f"Worker {worker_id} 使用数据库策略代码")

        # 从 trading_config 获取交易配置
        trading_config = worker.get_trading_config_dict()
        symbols_config = trading_config.get('symbols_config', {})
        symbols = symbols_config.get('symbols', ['BTCUSDT'])
        
        # 准备策略配置
        config = {
            "strategy_id": worker.strategy_id,
            "exchange": trading_config.get('exchange', 'binance'),
            "symbol": symbols[0] if symbols else 'BTCUSDT',  # 兼容旧版本，使用第一个货币对
            "symbols": symbols,  # 传递所有货币对
            "timeframe": trading_config.get('timeframe', '1h'),
            "market_type": trading_config.get('market_type', 'spot'),
            "trading_mode": trading_config.get('trading_mode', 'paper'),
            "cpu_limit": worker.cpu_limit,
            "memory_limit": worker.memory_limit,
            "config": worker.get_config_dict(),
            "strategy_code": strategy_code,  # 传递策略代码
        }
        
        # 先更新状态为 starting，表示正在启动中
        logger.info(f"[start_worker] Worker {worker_id} 状态变更: {worker.status} -> starting")
        worker.status = "starting"
        worker.started_at = datetime.now()
        db.commit()
        logger.info(f"[start_worker] Worker {worker_id} 已更新为 starting 状态")

        # 真正创建并启动 Worker 进程
        logger.info(f"[start_worker] Worker {worker_id} 开始调用 manager.start_strategy()")
        result_worker_id = await manager.start_strategy(
            strategy_path=strategy_path,
            config=config,
            worker_id=str(worker_id)
        )
        logger.info(f"[start_worker] Worker {worker_id} manager.start_strategy() 返回: {result_worker_id}")

        if not result_worker_id:
            # 启动失败，更新状态为 error
            logger.error(f"[start_worker] Worker {worker_id} start_strategy 返回 None，更新状态为 error")
            worker.status = "error"
            worker.pid = None
            db.commit()
            raise HTTPException(status_code=500, detail="Worker启动失败")

        # Worker 启动成功，更新状态为 running
        logger.info(f"[start_worker] Worker {worker_id} 启动成功，更新状态为 running")
        worker.status = "running"
        worker.pid = manager.get_worker_pid(str(worker_id))
        db.commit()
        logger.info(f"[start_worker] Worker {worker_id} 已更新为 running 状态，pid={worker.pid}")

        return schemas.ApiResponse(
            code=0,
            message="Worker启动成功",
            data={"worker_id": worker_id, "status": "running", "pid": worker.pid}
        )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动Worker失败: {str(e)}")


@router.post("/{worker_id}/lifecycle/stop", response_model=schemas.ApiResponse)
async def stop_worker(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user)
):
    """
    停止Worker
    
    停止Worker进程并更新数据库状态
    """
    try:
        worker = crud.get_worker(db, worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker不存在")
        
        # 检查 Worker 是否已停止
        if worker.status == "stopped":
            return schemas.ApiResponse(
                code=0,
                message="Worker已处于停止状态",
                data={"worker_id": worker_id, "status": "stopped"}
            )
        
        # 获取 WorkerManager 实例并停止 Worker 进程
        manager = await get_worker_manager()
        success = await manager.stop_worker(str(worker_id))
        
        if success:
            # 更新 Worker 状态为 stopped
            worker.status = "stopped"
            worker.pid = None
            worker.started_at = None  # 清空启动时间，这样运行时长就不会继续计算
            worker.stopped_at = datetime.now()
            db.commit()
            
            return schemas.ApiResponse(
                code=0,
                message="Worker停止成功",
                data={"worker_id": worker_id, "status": "stopped"}
            )
        else:
            raise HTTPException(status_code=500, detail="Worker停止失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止Worker失败: {str(e)}")


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
        success = await service.pause_worker(worker_id, db)
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
        success = await service.resume_worker(worker_id, db)
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
    level: Optional[str] = Query(None, description="日志级别筛选 (DEBUG/INFO/WARNING/ERROR)"),
    start_time: Optional[datetime] = Query(None, description="开始时间 (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="结束时间 (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数 (1-1000)"),
    offset: int = Query(0, ge=0, description="偏移量（用于分页）"),
    db: Session = Depends(get_db_session),  # 保留参数但不再使用
    current_user: dict = Depends(get_current_user)
):
    """
    获取 Worker 日志（基于文件系统 - 高性能方案）

    改进：
    - 直接从日志文件读取，性能提升10倍+
    - 支持分页查询
    - 无数据库压力
    """
    try:
        from ..service import get_log_file_manager

        # 使用 LogFileReader 查询日志
        log_mgr = get_log_file_manager()
        reader = log_mgr.get_reader(str(worker_id))

        logs, total = reader.query_logs(
            worker_id=str(worker_id),
            start_time=start_time,
            end_time=end_time,
            level=level,
            limit=limit,
            offset=offset,
        )

        return schemas.ApiResponse(
            code=0,
            message="success",
            data={
                "items": logs,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} 的日志文件不存在")
    except Exception as e:
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

    安全措施：
    - 需要确认参数
    - 记录操作审计日志
    """
    try:
        from ..service import get_log_file_manager

        # 安全检查：如果清理全部日志，需要明确确认
        if before_days is None and not confirm:
            return schemas.ApiResponse(
                code=400,
                message="危险操作：清理全部日志需要 confirm=true 参数",
                data=None
            )

        # 使用 LogFileReader 清理日志文件
        log_mgr = get_log_file_manager()
        reader = log_mgr.get_reader(str(worker_id))

        deleted_count = reader.clear_logs(
            worker_id=str(worker_id),
            before_days=before_days,
        )

        # 审计日志
        logger.info(
            f"用户 {current_user.get('username')} 清理了 Worker {worker_id} 的日志文件, "
            f"删除 {deleted_count} 个文件, before_days={before_days}"
        )

        return schemas.ApiResponse(
            code=0,
            message=f"成功清理 {deleted_count} 个日志文件",
            data={"deleted_count": deleted_count}
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
