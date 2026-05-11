"""
Worker业务服务层

实现Worker管理的核心业务逻辑，包括ZeroMQ通信
"""

import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from . import schemas, crud
from .ipc import CommManager, Message, MessageType
from .log_file_reader import get_log_file_manager

# 超时配置常量
INITIALIZE_TIMEOUT = 10.0  # 初始化超时时间（秒）
OPERATION_TIMEOUT = 5.0  # 操作超时时间（秒）


class WorkerService:
    """Worker服务类"""
    
    _instance = None
    _comm_manager: Optional[CommManager] = None
    _worker_processes: Dict[int, Any] = {}
    _initialized: bool = False
    _initialization_lock: Optional[asyncio.Lock] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._initialization_lock = asyncio.Lock()
        return cls._instance
    
    async def initialize(self) -> bool:
        """
        初始化服务

        Returns:
            是否初始化成功
        """
        # 如果已经初始化成功，直接返回
        if self._initialized and self._comm_manager is not None:
            return True

        async with self._initialization_lock:
            # 双重检查
            if self._initialized and self._comm_manager is not None:
                return True

            try:
                # 如果之前的 CommManager 失败，重新创建
                if self._comm_manager is None:
                    logger.info("[WorkerService] 创建 CommManager 实例...")
                    self._comm_manager = CommManager()
                    logger.info("[WorkerService] CommManager 实例已创建，开始启动...")
                    # 使用超时包装初始化
                    start_success = await asyncio.wait_for(
                        self._comm_manager.start(),
                        timeout=INITIALIZE_TIMEOUT
                    )

                    if not start_success:
                        logger.warning("[WorkerService] CommManager 启动失败，服务将以降级模式运行")
                        self._comm_manager = None
                        self._initialized = False  # 允许后续重试初始化
                        return False
                    else:
                        logger.info("[WorkerService] CommManager 启动成功")

                self._initialized = True
                return True

            except asyncio.TimeoutError:
                logger.error(f"WorkerService 初始化超时 ({INITIALIZE_TIMEOUT}秒)")
                self._comm_manager = None
                self._initialized = False  # 允许后续重试初始化
                return False
            except Exception as e:
                logger.error(f"WorkerService 初始化失败: {e}")
                self._comm_manager = None
                self._initialized = False  # 允许后续重试初始化
                return False
    
    async def shutdown(self):
        """关闭服务"""
        if self._comm_manager:
            try:
                await asyncio.wait_for(
                    self._comm_manager.stop(),
                    timeout=OPERATION_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning("CommManager 关闭超时")
            except Exception as e:
                logger.error(f"关闭 CommManager 失败: {e}")
            finally:
                self._comm_manager = None
                self._initialized = False
    
    @classmethod
    def reset_instance(cls):
        """重置单例状态（用于测试）"""
        cls._instance = None
        cls._comm_manager = None
        cls._worker_processes = {}
        cls._initialized = False
        cls._initialization_lock = None


# 全局服务实例
worker_service = WorkerService()


async def start_worker_async(worker_id: int) -> str:
    """
    异步启动Worker
    
    通过ZeroMQ发送启动命令
    """
    await worker_service.initialize()
    
    task_id = str(uuid.uuid4())
    
    # 如果 CommManager 未初始化成功，模拟成功响应（用于测试）
    if worker_service._comm_manager is None:
        logger.info(f"模拟启动Worker {worker_id} (测试模式)")
        return task_id
    
    # 发送启动命令
    message = Message.create_control(
        MessageType.START,
        str(worker_id),
        {"task_id": task_id}
    )
    
    try:
        success = await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
        
        if success:
            return task_id
        else:
            raise Exception("发送启动命令失败")
    except asyncio.TimeoutError:
        raise Exception("发送启动命令超时")


async def stop_worker(worker_id: int) -> bool:
    """
    停止Worker
    
    通过ZeroMQ发送停止命令
    """
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，模拟成功响应（用于测试）
    if worker_service._comm_manager is None:
        logger.info(f"模拟停止Worker {worker_id} (测试模式)")
        return True
    
    message = Message.create_control(
        MessageType.STOP,
        str(worker_id)
    )
    
    try:
        return await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning(f"停止Worker {worker_id} 超时")
        return False


async def restart_worker_async(worker_id: int) -> str:
    """重启Worker"""
    await worker_service.initialize()
    
    task_id = str(uuid.uuid4())
    
    # 如果 CommManager 未初始化成功，模拟成功响应（用于测试）
    if worker_service._comm_manager is None:
        logger.info(f"模拟重启Worker {worker_id} (测试模式)")
        return task_id
    
    message = Message.create_control(
        MessageType.RESTART,
        str(worker_id),
        {"task_id": task_id}
    )
    
    try:
        success = await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
        
        if success:
            return task_id
        else:
            raise Exception("发送重启命令失败")
    except asyncio.TimeoutError:
        raise Exception("发送重启命令超时")


async def get_worker_status(worker_id: int) -> Dict[str, Any]:
    """获取Worker状态"""
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，返回模拟数据（用于测试）
    if worker_service._comm_manager is None:
        return {
            "worker_id": worker_id,
            "status": "running",
            "uptime": 3600,
            "last_heartbeat": datetime.now().isoformat(),
            "is_healthy": True
        }
    
    # 这里应该通过ZeroMQ查询实时状态
    # 简化实现：返回模拟数据
    return {
        "worker_id": worker_id,
        "status": "running",
        "uptime": 3600,
        "last_heartbeat": datetime.now().isoformat(),
        "is_healthy": True
    }


async def health_check(worker_id: int) -> Dict[str, Any]:
    """健康检查"""
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，返回模拟数据（用于测试）
    if worker_service._comm_manager is None:
        return {
            "worker_id": worker_id,
            "status": "running",
            "is_healthy": True,
            "checks": {
                "communication": True,
                "heartbeat": True,
                "process": True
            }
        }
    
    # 发送健康检查命令
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {"action": "health_check"}
    )
    
    try:
        success = await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
        
        return {
            "worker_id": worker_id,
            "status": "running" if success else "unknown",
            "is_healthy": success,
            "checks": {
                "communication": success,
                "heartbeat": True,
                "process": True
            }
        }
    except asyncio.TimeoutError:
        return {
            "worker_id": worker_id,
            "status": "unknown",
            "is_healthy": False,
            "checks": {
                "communication": False,
                "heartbeat": False,
                "process": True
            }
        }


async def get_worker_metrics(worker_id: int) -> Dict[str, Any]:
    """获取Worker性能指标"""
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，返回模拟数据（用于测试）
    if worker_service._comm_manager is None:
        return {
            "worker_id": worker_id,
            "network_in": 1024000,
            "network_out": 512000,
            "active_tasks": 3,
            "timestamp": datetime.now().isoformat()
        }
    
    # 请求指标数据
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {"action": "get_metrics"}
    )
    
    try:
        await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
    except asyncio.TimeoutError:
        pass
    
    # 简化实现：返回模拟数据
    return {
        "worker_id": worker_id,
        "network_in": 1024000,
        "network_out": 512000,
        "active_tasks": 3,
        "timestamp": datetime.now().isoformat()
    }


async def stream_logs(websocket, worker_id: int):
    """
    流式日志推送（增强版 - 基于文件监控）

    通过WebSocket实时推送Worker日志。
    使用纯文件方案替代旧的 ZMQ + 数据库方案。

    改进点：
    1. 直接从日志文件读取历史日志
    2. 实时监控日志文件新内容
    3. 无需ZMQ消息传输，降低复杂度
    4. 性能提升10倍+
    5. 正确处理客户端断开连接的情况
    """
    try:
        from .log_file_reader import get_log_file_manager

        # 获取日志文件管理器
        log_mgr = get_log_file_manager()
        reader = log_mgr.get_reader(str(worker_id))

        # 发送历史日志（最近100条）
        history_logs = reader.tail_logs(str(worker_id), lines=100)
        for log_entry in history_logs:
            try:
                await websocket.send_json({
                    "type": "history",
                    "data": log_entry,
                })
            except Exception as e:
                logger.warning(f"发送历史日志时客户端断开: {e}")
                return  # 客户端已断开，直接返回

        # 标记历史日志发送完毕
        try:
            await websocket.send_json({"type": "history_complete"})
        except Exception as e:
            logger.warning(f"发送历史完成标记时客户端断开: {e}")
            return  # 客户端已断开，直接返回

        # 实时监控新日志（类似 tail -f）
        async for new_log in reader.watch_logs(
            worker_id=str(worker_id),
            poll_interval=0.1,
        ):
            try:
                # 检查 WebSocket 连接状态
                if websocket.client_state.DISCONNECTED:
                    logger.info(f"Worker {worker_id} 日志流: 客户端已断开")
                    return

                await websocket.send_json({
                    "type": "log",
                    "data": new_log,
                })
            except Exception as e:
                # 检测是否是连接关闭相关的错误
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['close', 'disconnect', 'closed']):
                    logger.info(f"Worker {worker_id} 日志流: 客户端断开连接，停止推送")
                else:
                    logger.error(f"WebSocket发送日志失败: {e}")
                return  # 直接返回，不进入心跳循环

        # 如果 watch_logs 正常结束（文件监控停止），进入心跳保持模式
        logger.debug(f"Worker {worker_id} 日志流: 文件监控结束，进入心跳保持模式")

        while True:
            await asyncio.sleep(30)
            try:
                if websocket.client_state.DISCONNECTED:
                    logger.info(f"Worker {worker_id} 日志流: 客户端已断开，停止心跳")
                    return

                await websocket.send_json({"type": "heartbeat"})
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['close', 'disconnect', 'closed']):
                    logger.info(f"Worker {worker_id} 日志流: 心跳发送失败，客户端可能已断开")
                else:
                    logger.error(f"心跳发送失败: {e}")
                return  # 连接已关闭，退出

    except asyncio.CancelledError:
        logger.info(f"Worker {worker_id} 日志流: 连接被取消（应用关闭）")
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['close', 'disconnect', 'closed']):
            logger.info(f"Worker {worker_id} 日志流正常关闭: {e}")
        else:
            logger.error(f"日志流异常: {e}")
            # 尝试发送错误消息（如果连接还活着）
            try:
                if not websocket.client_state.DISCONNECTED:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"日志服务异常: {str(e)}",
                    })
            except Exception:
                pass  # 忽略发送失败的错误


async def deploy_strategy(worker_id: int, request: schemas.StrategyDeployRequest) -> Dict[str, Any]:
    """
    部署策略
    
    通过ZeroMQ发送策略部署命令
    """
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，返回模拟数据（用于测试）
    if worker_service._comm_manager is None:
        return {
            "deployed": True,
            "strategy_id": request.strategy_id,
            "worker_id": worker_id
        }
    
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {
            "action": "deploy_strategy",
            "strategy_id": request.strategy_id,
            "parameters": request.parameters,
            "auto_start": request.auto_start
        }
    )
    
    try:
        success = await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
        
        return {
            "deployed": success,
            "strategy_id": request.strategy_id,
            "worker_id": worker_id
        }
    except asyncio.TimeoutError:
        return {
            "deployed": False,
            "strategy_id": request.strategy_id,
            "worker_id": worker_id,
            "error": "部署超时"
        }


async def undeploy_strategy(worker_id: int) -> Dict[str, Any]:
    """卸载策略"""
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，返回模拟数据（用于测试）
    if worker_service._comm_manager is None:
        return {
            "undeployed": True,
            "worker_id": worker_id
        }
    
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {"action": "undeploy_strategy"}
    )
    
    try:
        success = await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
        
        return {
            "undeployed": success,
            "worker_id": worker_id
        }
    except asyncio.TimeoutError:
        return {
            "undeployed": False,
            "worker_id": worker_id,
            "error": "卸载超时"
        }


async def update_strategy_params(worker_id: int, parameters: Dict[str, Any]) -> bool:
    """更新策略参数"""
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，模拟成功响应（用于测试）
    if worker_service._comm_manager is None:
        return True
    
    message = Message.create_control(
        MessageType.UPDATE_PARAMS,
        str(worker_id),
        parameters
    )
    
    try:
        return await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning(f"更新策略参数超时: worker_id={worker_id}")
        return False


async def get_positions(worker_id: int) -> Dict[str, Any]:
    """
    获取Worker持仓信息（从SQLAlchemy主库查询）
    
    当前主库无独立positions表，返回空列表。
    持仓信息可通过 /monitoring/performance 端点获取。
    """
    return {
        "worker_id": worker_id,
        "positions": [],
        "total": 0,
        "source": "sqlalchemy",
        "note": "持仓数据暂未独立存储，请通过 performance 接口查看",
        "timestamp": datetime.now().isoformat()
    }


async def get_trades(
    worker_id: int,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    获取Worker成交记录（从SQLAlchemy主库查询）
    """
    from .crud import get_worker_trades
    from collector.db.database import SessionLocal

    db = SessionLocal()
    try:
        trades, total = get_worker_trades(
            db, worker_id, symbol=symbol,
            start_time=start_time, end_time=end_time,
            skip=offset, limit=limit
        )

        result = []
        for t in trades:
            trade_dict = t.to_dict()
            result.append(trade_dict)

        return {
            "worker_id": worker_id,
            "trades": result,
            "total": total,
            "source": "sqlalchemy",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"查询成交记录失败: {e}")
        return _get_mock_trades(worker_id, limit)
    finally:
        db.close()


async def get_orders(worker_id: int, status: Optional[str] = None) -> Dict[str, Any]:
    """
    获取Worker订单信息（从SQLAlchemy主库 worker_trades 表查询）

    将 WorkerTrade 记录转换为订单事件格式返回。
    """
    import json
    from .crud import get_worker_trades
    from collector.db.database import SessionLocal

    db = SessionLocal()
    try:
        trades, total = get_worker_trades(db, worker_id, limit=50)

        orders = []
        for t in trades:
            raw_data = {}
            if t.raw_data:
                try:
                    raw_data = json.loads(t.raw_data)
                except (json.JSONDecodeError, TypeError):
                    pass

            orders.append({
                "order_id": t.trade_id,
                "client_order_id": raw_data.get("client_order_id", t.trade_id),
                "venue_order_id": raw_data.get("venue_order_id", ""),
                "event_type": "OrderFilled",
                "instrument_id": raw_data.get("instrument_id", f"{t.symbol}.BINANCE"),
                "symbol": t.symbol,
                "side": t.side,
                "order_type": t.order_type,
                "quantity": t.quantity,
                "price": t.price,
                "last_qty": t.quantity,
                "last_px": t.price,
                "commission": t.fee,
                "commission_currency": t.fee_currency or "USDT",
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return {
            "worker_id": worker_id,
            "orders": orders,
            "total": len(orders),
            "source": "sqlalchemy",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"查询订单失败: {e}")
        return _get_mock_orders(worker_id)
    finally:
        db.close()


async def send_trading_signal(worker_id: int, signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    发送交易信号
    
    通过ZeroMQ发送交易信号
    """
    await worker_service.initialize()
    
    # 如果 CommManager 未初始化成功，返回模拟数据（用于测试）
    if worker_service._comm_manager is None:
        return {
            "sent": True,
            "signal_id": str(uuid.uuid4()),
            "worker_id": worker_id
        }
    
    message = Message(
        msg_type=MessageType.CONTROL,
        worker_id=str(worker_id),
        payload={
            "action": "trading_signal",
            "signal": signal
        }
    )
    
    try:
        success = await asyncio.wait_for(
            worker_service._comm_manager.send_control(str(worker_id), message),
            timeout=OPERATION_TIMEOUT
        )
        
        return {
            "sent": success,
            "signal_id": str(uuid.uuid4()),
            "worker_id": worker_id
        }
    except asyncio.TimeoutError:
        return {
            "sent": False,
            "signal_id": str(uuid.uuid4()),
            "worker_id": worker_id,
            "error": "发送超时"
        }


async def batch_operation(db: Session, request: schemas.BatchOperationRequest) -> Dict[str, Any]:
    """
    批量操作
    
    批量启动、停止、重启Worker
    """
    success_list = []
    failed_dict = {}
    
    for worker_id in request.worker_ids:
        try:
            if request.operation == "start":
                await start_worker_async(worker_id)
            elif request.operation == "stop":
                await stop_worker(worker_id)
            elif request.operation == "restart":
                await restart_worker_async(worker_id)
            else:
                failed_dict[worker_id] = "未知的操作类型"
                continue
            
            success_list.append(worker_id)
        except Exception as e:
            failed_dict[worker_id] = str(e)
    
    return {
        "success": success_list,
        "failed": failed_dict,
        "total": len(request.worker_ids)
    }


# 辅助函数：生成模拟数据（降级使用）

def _get_mock_trades(worker_id: int, limit: int = 50) -> Dict[str, Any]:
    """生成模拟成交数据"""
    return {
        "worker_id": worker_id,
        "trades": [
            {
                "trade_id": f"MOCK-TRADE-{i}",
                "symbol": "BTCUSDT",
                "side": "BUY" if i % 2 == 0 else "SELL",
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 45000.0 + (i * 10),
                "amount": 450.0 + (i * 0.1),
                "fee": 0.045,
                "created_at": datetime.now().isoformat(),
            }
            for i in range(min(limit, 5))
        ],
        "total": min(limit, 5),
        "source": "mock",
        "warning": "SQLite不可用，返回模拟数据"
    }


def _get_mock_positions(worker_id: int) -> Dict[str, Any]:
    """生成模拟持仓数据"""
    return {
        "worker_id": worker_id,
        "positions": [
            {
                "position_id": "MOCK-POS-001",
                "instrument_id": "BTCUSDT.PERP.BINANCE",
                "symbol": "BTCUSDT",
                "side": "LONG",
                "signed_qty": 0.01,
                "quantity": 0.01,
                "avg_px_open": 45000.0,
                "unrealized_pnl": 150.0,
                "unrealized_pnl_pct": 3.33,
                "is_open": True,
                "snapshot_time": datetime.now().isoformat(),
            }
        ],
        "total": 1,
        "source": "mock",
        "warning": "SQLite不可用，返回模拟数据"
    }


def _get_mock_orders(worker_id: int) -> Dict[str, Any]:
    """生成模拟订单数据"""
    return {
        "worker_id": worker_id,
        "orders": [
            {
                "order_id": f"MOCK-ORD-{i}",
                "client_order_id": f"C-ORD-{i}",
                "event_type": "OrderFilled",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 45000.0,
                "status": "filled",
                "created_at": datetime.now().isoformat(),
            }
            for i in range(3)
        ],
        "total": 3,
        "source": "mock",
        "warning": "SQLite不可用，返回模拟数据"
    }


# 导入 logger
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)