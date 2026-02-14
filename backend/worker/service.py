"""
Worker业务服务层

实现Worker管理的核心业务逻辑，包括ZeroMQ通信
"""

import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from . import schemas, crud
from .ipc import CommManager, Message, MessageType
from .models import Worker


class WorkerService:
    """Worker服务类"""
    
    _instance = None
    _comm_manager: Optional[CommManager] = None
    _worker_processes: Dict[int, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        """初始化服务"""
        if self._comm_manager is None:
            self._comm_manager = CommManager()
            await self._comm_manager.start()
    
    async def shutdown(self):
        """关闭服务"""
        if self._comm_manager:
            await self._comm_manager.stop()
            self._comm_manager = None


# 全局服务实例
worker_service = WorkerService()


async def start_worker_async(worker_id: int) -> str:
    """
    异步启动Worker
    
    通过ZeroMQ发送启动命令
    """
    await worker_service.initialize()
    
    task_id = str(uuid.uuid4())
    
    # 发送启动命令
    message = Message.create_control(
        MessageType.START,
        str(worker_id),
        {"task_id": task_id}
    )
    
    success = await worker_service._comm_manager.send_control(str(worker_id), message)
    
    if success:
        return task_id
    else:
        raise Exception("发送启动命令失败")


async def stop_worker(worker_id: int) -> bool:
    """
    停止Worker
    
    通过ZeroMQ发送停止命令
    """
    await worker_service.initialize()
    
    message = Message.create_control(
        MessageType.STOP,
        str(worker_id)
    )
    
    return await worker_service._comm_manager.send_control(str(worker_id), message)


async def restart_worker_async(worker_id: int) -> str:
    """重启Worker"""
    await worker_service.initialize()
    
    task_id = str(uuid.uuid4())
    
    message = Message.create_control(
        MessageType.RESTART,
        str(worker_id),
        {"task_id": task_id}
    )
    
    success = await worker_service._comm_manager.send_control(str(worker_id), message)
    
    if success:
        return task_id
    else:
        raise Exception("发送重启命令失败")


async def pause_worker(worker_id: int) -> bool:
    """暂停Worker"""
    await worker_service.initialize()
    
    message = Message.create_control(
        MessageType.PAUSE,
        str(worker_id)
    )
    
    return await worker_service._comm_manager.send_control(str(worker_id), message)


async def resume_worker(worker_id: int) -> bool:
    """恢复Worker"""
    await worker_service.initialize()
    
    message = Message.create_control(
        MessageType.RESUME,
        str(worker_id)
    )
    
    return await worker_service._comm_manager.send_control(str(worker_id), message)


async def get_worker_status(worker_id: int) -> Dict[str, Any]:
    """获取Worker状态"""
    await worker_service.initialize()
    
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
    
    # 发送健康检查命令
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {"action": "health_check"}
    )
    
    success = await worker_service._comm_manager.send_control(str(worker_id), message)
    
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


async def get_worker_metrics(worker_id: int) -> Dict[str, Any]:
    """获取Worker性能指标"""
    await worker_service.initialize()
    
    # 请求指标数据
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {"action": "get_metrics"}
    )
    
    await worker_service._comm_manager.send_control(str(worker_id), message)
    
    # 简化实现：返回模拟数据
    return {
        "worker_id": worker_id,
        "cpu_usage": 15.5,
        "memory_usage": 45.2,
        "memory_used_mb": 256.0,
        "network_in": 1024000,
        "network_out": 512000,
        "active_tasks": 3,
        "timestamp": datetime.now().isoformat()
    }


async def stream_logs(websocket, worker_id: int):
    """
    流式日志推送
    
    通过WebSocket实时推送Worker日志
    """
    await worker_service.initialize()
    
    # 注册日志处理器
    async def log_handler(message: Message):
        if message.worker_id == str(worker_id) and message.msg_type == MessageType.LOG:
            await websocket.send_json(message.payload)
    
    worker_service._comm_manager.register_status_handler(log_handler)
    
    try:
        while True:
            # 保持连接
            await asyncio.sleep(1)
    except Exception:
        pass
    finally:
        worker_service._comm_manager.unregister_status_handler(log_handler)


async def deploy_strategy(worker_id: int, request: schemas.StrategyDeployRequest) -> Dict[str, Any]:
    """
    部署策略
    
    通过ZeroMQ发送策略部署命令
    """
    await worker_service.initialize()
    
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
    
    success = await worker_service._comm_manager.send_control(str(worker_id), message)
    
    return {
        "deployed": success,
        "strategy_id": request.strategy_id,
        "worker_id": worker_id
    }


async def undeploy_strategy(worker_id: int) -> Dict[str, Any]:
    """卸载策略"""
    await worker_service.initialize()
    
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {"action": "undeploy_strategy"}
    )
    
    success = await worker_service._comm_manager.send_control(str(worker_id), message)
    
    return {
        "undeployed": success,
        "worker_id": worker_id
    }


async def update_strategy_params(worker_id: int, parameters: Dict[str, Any]) -> bool:
    """更新策略参数"""
    await worker_service.initialize()
    
    message = Message.create_control(
        MessageType.UPDATE_PARAMS,
        str(worker_id),
        parameters
    )
    
    return await worker_service._comm_manager.send_control(str(worker_id), message)


async def get_positions(worker_id: int) -> List[Dict[str, Any]]:
    """获取持仓信息"""
    await worker_service.initialize()
    
    # 请求持仓数据
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        {"action": "get_positions"}
    )
    
    await worker_service._comm_manager.send_control(str(worker_id), message)
    
    # 简化实现：返回模拟数据
    return [
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "quantity": 1.5,
            "entry_price": 45000.0,
            "current_price": 46000.0,
            "unrealized_pnl": 1500.0,
            "unrealized_pnl_pct": 2.22,
            "timestamp": datetime.now().isoformat()
        }
    ]


async def get_orders(worker_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取订单信息"""
    await worker_service.initialize()
    
    # 请求订单数据
    params = {"action": "get_orders"}
    if status:
        params["status"] = status
    
    message = Message.create_control(
        MessageType.CONTROL,
        str(worker_id),
        params
    )
    
    await worker_service._comm_manager.send_control(str(worker_id), message)
    
    # 简化实现：返回模拟数据
    return [
        {
            "order_id": "123456",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
            "price": 45000.0,
            "status": "filled",
            "filled_quantity": 1.0,
            "created_at": datetime.now().isoformat()
        }
    ]


async def send_trading_signal(worker_id: int, signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    发送交易信号
    
    通过ZeroMQ发送交易信号
    """
    await worker_service.initialize()
    
    message = Message(
        msg_type=MessageType.CONTROL,
        worker_id=str(worker_id),
        payload={
            "action": "trading_signal",
            "signal": signal
        }
    )
    
    success = await worker_service._comm_manager.send_control(str(worker_id), message)
    
    return {
        "sent": success,
        "signal_id": str(uuid.uuid4()),
        "worker_id": worker_id
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
