"""
Worker API路由定义

整合所有Worker相关的API端点
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, WebSocket, Request
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

async def shutdown_worker_manager():
    """停止 WorkerManager，清理所有 Worker 进程
    
    在应用关闭时调用，确保所有 Worker 进程被优雅停止：
    1. 发送 STOP 命令给所有 Worker
    2. 等待 Worker 正常退出（超时 30 秒）
    3. 强制终止未退出的 Worker
    4. 清理通信资源（ZMQ socket、端口等）
    """
    global _worker_manager
    if _worker_manager is not None:
        try:
            logger.info("正在停止 WorkerManager，清理所有 Worker 进程...")
            await _worker_manager.stop()
            logger.info("WorkerManager 已成功停止")
        except Exception as e:
            error_type = type(e).__name__
            if 'attached to a different loop' in str(e) or 'different loop' in str(e):
                logger.info(f"WorkerManager 停止中（事件循环已关闭）")
            else:
                logger.error(f"停止 WorkerManager 失败 ({error_type}): {e}")
        finally:
            _worker_manager = None
    else:
        logger.info("WorkerManager 未初始化，无需停止")


async def get_worker_manager():
    """
    获取 TradingNodeWorkerManager 实例（懒加载）

    使用 TradingNodeWorkerManager 以支持 Nautilus Trader 框架集成，
    确保策略运行时能正确初始化 TradingNode 并输出完整日志。
    """
    global _worker_manager
    if _worker_manager is None:
        from ..manager import TradingNodeWorkerManager
        _worker_manager = TradingNodeWorkerManager()
        # 注册 Worker 退出回调
        _worker_manager.register_worker_exit_callback(_on_worker_exit)
        # 启动 WorkerManager
        await _worker_manager.start()
        logger.info("TradingNodeWorkerManager 初始化并启动完成，已注册退出回调")
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
        
        # 获取策略信息（三层回退机制）
        strategy_path = None
        strategy_code = None
        strategy_found = False

        import json as json_lib
        worker_config = {}
        if worker.config:
            try:
                worker_config = json_lib.loads(worker.config) if isinstance(worker.config, str) else worker_config
            except Exception:
                pass

        strategy_file_name_from_config = worker_config.get('strategy_file_name')

        if worker.strategy_id or strategy_file_name_from_config:
            # Layer 1: 从数据库查询（最优先）
            if worker.strategy_id:
                from strategy.models import Strategy
                strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()

                if strategy:
                    strategy_found = True
                    if strategy.code:
                        strategy_code = strategy.code
                        logger.info(f"[策略加载] 使用数据库策略代码 (策略: {strategy.name}, ID: {strategy.id})")
                    elif strategy.file_name:
                        strategy_path = f"strategies/{strategy.file_name}"
                        logger.info(f"[策略加载] 使用策略文件名 (策略: {strategy.name}, 文件: {strategy.file_name})")
                    else:
                        logger.warning(f"[策略加载] 数据库策略缺少 code 和 file_name (ID: {strategy.id})")

            # Layer 2: 通过 strategy_file_name 参数查找（新增）
            if not strategy_found and strategy_file_name_from_config:
                file_name = strategy_file_name_from_config
                full_path = f"strategies/{file_name}"

                import os
                if os.path.exists(full_path):
                    strategy_path = full_path
                    strategy_found = True
                    logger.info(f"[策略加载] 通过文件名找到策略文件: {full_path}")
                else:
                    logger.warning(f"[策略加载] 策略文件不存在: {full_path}")

            # Layer 3: 文件系统扫描（兜底）
            if not strategy_found:
                logger.info("[策略加载] 数据库和精确文件名均未找到，开始文件系统扫描...")

                from pathlib import Path
                strategies_dir = Path("strategies")

                if strategies_dir.exists():
                    candidates = []

                    if worker.strategy_id:
                        candidates.append(f"{worker.strategy_id}.py")

                    if strategy_file_name_from_config:
                        candidates.append(strategy_file_name_from_config)

                    candidates.append(f"{worker.name.lower().replace(' ', '_')}.py")

                    for candidate in candidates:
                        candidate_path = strategies_dir / candidate
                        if candidate_path.exists():
                            strategy_path = str(candidate_path)
                            strategy_found = True
                            logger.info(f"[策略加载] 文件系统扫描找到策略: {candidate_path}")
                            break

                    if not strategy_found:
                        available_files = list(strategies_dir.glob("*.py"))
                        available_names = [f.stem for f in available_files if f.stem != "__init__"]
                        logger.error(
                            f"[策略加载] 策略文件未找到！\n"
                            f"   - strategy_id: {worker.strategy_id}\n"
                            f"   - strategy_file_name: {strategy_file_name_from_config}\n"
                            f"   - 可用策略文件: {available_names}"
                        )
                else:
                    logger.error(f"[策略加载] 策略目录不存在: {strategies_dir.absolute()}")

        # 最终检查
        if not strategy_code and not strategy_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"无法加载策略文件。"
                    f"strategy_id={worker.strategy_id}, "
                    f"请确认策略已正确配置或在数据库中存在。"
                )
            )

        # 记录实际使用的策略路径
        if strategy_path:
            logger.info(f"Worker {worker_id} 使用策略路径: {strategy_path}")
        if strategy_code:
            logger.info(f"Worker {worker_id} 使用数据库策略代码")

        # 从 trading_config 获取交易配置
        trading_config = worker.get_trading_config_dict()
        symbols_config = trading_config.get('symbols_config', {})
        symbols = symbols_config.get('symbols', ['BTCUSDT'])

        # 确定交易模式和账户类型
        # 支持多种市场类型: spot(现货), usdt_futures(U本位合约), coin_futures(币本位合约)
        market_type = trading_config.get('market_type', 'spot')
        account_type_map = {
            'spot': 'spot',
            'usdt_futures': 'usdt_futures',
            'coin_futures': 'coin_futures',
            'futures': 'usdt_futures',  # 兼容旧版本
        }
        account_type = account_type_map.get(market_type, 'spot')

        # 交易模式映射: live(实盘), testnet(模拟盘/测试网), paper(纸上交易)
        trading_mode = trading_config.get('trading_environment', trading_config.get('trading_mode', 'live'))

        # 从 SystemConfig 补充交易所 API 密钥（根据环境类型选择对应配置）
        exchange_id = trading_config.get('exchange', 'binance')

        # 根据环境类型确定 API 密钥字段名
        if trading_mode == 'testnet':
            api_key_field = 'testnet_api_key'
            api_secret_field = 'testnet_api_secret'
        elif trading_mode == 'paper':
            api_key_field = None  # 纸上交易不需要真实 API 密钥
            api_secret_field = None
        else:
            api_key_field = 'live_api_key'  # 优先使用 live_api_key
            api_secret_field = 'live_api_secret'

        exchange_api_key = trading_config.get('api_key')
        exchange_api_secret = trading_config.get('api_secret')
        exchange_api_passphrase = trading_config.get('api_passphrase')
        proxy_url = trading_config.get('proxy_url')

        if not exchange_api_key or not exchange_api_secret:
            from collector.db.models import SystemConfig as SystemConfigModel
            exchange_cfg_prefix = f"exchange.{exchange_id}."
            cfg_rows = db.query(SystemConfigModel).filter(
                SystemConfigModel.key.like(f"{exchange_cfg_prefix}%")
            ).all()
            cfg_map = {}
            for row in cfg_rows:
                field = row.key[len(exchange_cfg_prefix):]
                cfg_map[field] = row.value

            # 根据环境类型读取对应的 API 密钥
            if trading_mode == 'testnet':
                if not exchange_api_key:
                    exchange_api_key = cfg_map.get('testnet_api_key')
                if not exchange_api_secret:
                    exchange_api_secret = cfg_map.get('testnet_api_secret')
            elif trading_mode != 'paper':
                # live 环境：优先使用 live_api_key，回退到 api_key（兼容旧配置）
                if not exchange_api_key:
                    exchange_api_key = cfg_map.get('live_api_key') or cfg_map.get('api_key')
                if not exchange_api_secret:
                    exchange_api_secret = cfg_map.get('live_api_secret') or cfg_map.get('api_secret')

            if not exchange_api_passphrase:
                exchange_api_passphrase = cfg_map.get('api_passphrase')
            if not proxy_url and cfg_map.get('proxy_enabled') in (True, '1', 'true'):
                proxy_url = cfg_map.get('proxy_url')

            logger.info(
                f"Worker {worker_id} 从 SystemConfig 补充交易所密钥: "
                f"exchange={exchange_id}, "
                f"environment={trading_mode}, "
                f"api_key={'已配置' if exchange_api_key else '未配置'}, "
                f"api_secret={'已配置' if exchange_api_secret else '未配置'}"
            )

        # 准备策略配置（包含完整的 Nautilus Trader 集成配置）
        config = {
            # 基础配置
            "strategy_id": worker.strategy_id,
            "exchange": exchange_id,
            "symbol": symbols[0] if symbols else 'BTCUSDT',
            "symbols": symbols,
            "timeframe": trading_config.get('timeframe', '1h'),
            "market_type": market_type,

            # Nautilus Trader 标识和核心配置
            "worker_type": "nautilus",  # 标识使用 TradingNodeWorkerProcess

            # Nautilus 特定配置（传递给 TradingNode 初始化）
            "trading": {
                "exchange": exchange_id,
                "account_type": account_type,
                "trading_mode": trading_mode,  # live/demo/paper

                # API 密钥（优先从 worker trading_config 读取，其次从 SystemConfig 补充）
                "api_key": exchange_api_key,
                "api_secret": exchange_api_secret,
                "api_passphrase": exchange_api_passphrase,  # OKX需要

                # 代理配置
                "proxy_url": proxy_url,

                # 日志配置
                "log_level": "DEBUG",  # 使用 DEBUG 级别以便调试 NautilusTrader 日志问题
                # "log_directory": None,  # 使用默认临时目录
                # "log_file_name": f"worker_{worker_id}.log",
            },

            # 自定义配置
            "config": worker.get_config_dict(),

            # 策略代码（优先使用数据库中的代码）
            "strategy_code": strategy_code,

            # 策略参数（传递给策略构造函数）
            "params": trading_config.get('strategy_params', {}),
        }
        
        # 先更新状态为 starting，表示正在启动中
        logger.info(f"[start_worker] Worker {worker_id} 状态变更: {worker.status} -> starting")
        worker.status = "starting"
        worker.started_at = datetime.now()
        db.commit()
        logger.info(f"[start_worker] Worker {worker_id} 已更新为 starting 状态")

        # 真正创建并启动 TradingNode Worker 进程
        # 使用 start_trading_worker() 而非 start_strategy()，确保正确初始化 Nautilus Trader
        logger.info(f"[start_worker] Worker {worker_id} 开始调用 manager.start_trading_worker()")
        result_worker_id = await manager.start_trading_worker(
            strategy_path=strategy_path,
            config=config,
            worker_id=str(worker_id),
            exchange_config=config.get('trading'),  # 传递交易所配置
        )
        logger.info(f"[start_worker] Worker {worker_id} manager.start_trading_worker() 返回: {result_worker_id}")

        if not result_worker_id:
            # 启动失败，更新状态为 error
            logger.error(f"[start_worker] Worker {worker_id} start_trading_worker 返回 None，更新状态为 error")
            worker.status = "error"
            worker.pid = None
            db.commit()
            raise HTTPException(status_code=500, detail="Worker启动失败（Nautilus Trader 初始化失败）")

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


@router.get("/{worker_id}/monitoring/logs/stream")
async def log_stream_sse(
    worker_id: int,
    request: Request,
    token: Optional[str] = Query(None, description="JWT token for SSE authentication (EventSource cannot send headers)")
):
    """
    SSE 实时日志流 (推荐方案)

    通过 Server-Sent Events 实时推送 Worker 日志。
    使用 FastAPI 0.136.1+ 内置的 EventSourceResponse，无需额外依赖。

    认证说明：
    - EventSource API 无法发送自定义请求头（浏览器安全限制）
    - 因此支持通过 query 参数传递 JWT token
    - 如果未提供 token，开发环境允许匿名访问

    相比 WebSocket，SSE 具有以下优势：
    1. 浏览器原生支持自动重连
    2. 无需特殊代理配置
    3. 自动处理断点续传（Last-Event-ID）
    4. 更低的资源占用
    """
    from ..dependencies import get_current_user

    current_user = await get_current_user(request, token=token)
    from fastapi.responses import EventSourceResponse
    from fastapi.sse import format_sse_event, KEEPALIVE_COMMENT
    import json as json_module
    from ..log_file_reader import get_log_file_manager

    log_mgr = get_log_file_manager()
    reader = log_mgr.get_reader(str(worker_id))

    async def event_generator():
        logger.info(f"Worker {worker_id} SSE 日志流: 开始生成事件流")
        try:
            history_logs = reader.tail_logs(str(worker_id), lines=100)
            logger.info(f"SSE 日志流: tail_logs 返回 {len(history_logs)} 条历史日志, 类型={type(history_logs).__name__}")
            for idx, log_entry in enumerate(history_logs):
                if await request.is_disconnected():
                    logger.info(f"SSE 日志流: 客户端已断开 (history #{idx})")
                    break
                logger.debug(f"SSE 日志流: yield history #{idx}, type={type(log_entry).__name__}")
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
                logger.debug(f"SSE 日志流: yield log #{event_id}, type={type(new_log).__name__}")
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
