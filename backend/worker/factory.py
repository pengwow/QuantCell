#!/usr/bin/env python3
"""
Worker 工厂模块

根据配置创建不同类型的 Worker 进程。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .worker_process import WorkerProcess, TradingNodeWorkerProcess


def create_worker(
    worker_id: str,
    strategy_path: str,
    config: dict,
    comm_host: str = "127.0.0.1",
    data_port: int = 5555,
    control_port: int = 5556,
    status_port: int = 5557,
) -> "WorkerProcess | TradingNodeWorkerProcess":
    """
    创建 Worker 进程

    Parameters
    ----------
    worker_id : str
        Worker ID
    strategy_path : str
        策略文件路径
    config : dict
        Worker 配置
    comm_host : str
        通信主机地址
    data_port : int
        数据端口
    control_port : int
        控制端口
    status_port : int
        状态端口

    Returns
    -------
    WorkerProcess | TradingNodeWorkerProcess
        Worker 进程实例
    """
    # 从配置中确定 Worker 类型
    worker_type = config.get("worker_type", "standard")

    if worker_type == "nautilus":
        # 创建 TradingNode Worker
        from .worker_process import TradingNodeWorkerProcess

        return TradingNodeWorkerProcess(
            worker_id=worker_id,
            strategy_path=strategy_path,
            config=config,
            comm_host=comm_host,
            data_port=data_port,
            control_port=control_port,
            status_port=status_port,
        )
    else:
        # 创建标准 Worker
        from .worker_process import WorkerProcess

        return WorkerProcess(
            worker_id=worker_id,
            strategy_path=strategy_path,
            config=config,
            comm_host=comm_host,
            data_port=data_port,
            control_port=control_port,
            status_port=status_port,
        )


def create_nautilus_worker(
    worker_id: str,
    strategy_path: str,
    config: dict,
    exchange: str = "binance",
    account_type: str = "spot",
    trading_mode: str = "demo",
    comm_host: str = "127.0.0.1",
    data_port: int = 5555,
    control_port: int = 5556,
    status_port: int = 5557,
) -> "TradingNodeWorkerProcess":
    """
    创建 Nautilus TradingNode Worker

    Parameters
    ----------
    worker_id : str
        Worker ID
    strategy_path : str
        策略文件路径
    config : dict
        Worker 配置
    exchange : str
        交易所 (binance/okx)
    account_type : str
        账户类型 (spot/usdt_futures/coin_futures)
    trading_mode : str
        交易模式 (live/demo/paper)
    comm_host : str
        通信主机地址
    data_port : int
        数据端口
    control_port : int
        控制端口
    status_port : int
        状态端口

    Returns
    -------
    TradingNodeWorkerProcess
        TradingNode Worker 进程实例
    """
    from .worker_process import TradingNodeWorkerProcess

    # 确保配置中包含 Nautilus 特定配置
    nautilus_config = config.get("nautilus", {})
    nautilus_config.update({
        "exchange": exchange,
        "account_type": account_type,
        "trading_mode": trading_mode,
    })
    config["nautilus"] = nautilus_config
    config["worker_type"] = "nautilus"

    return TradingNodeWorkerProcess(
        worker_id=worker_id,
        strategy_path=strategy_path,
        config=config,
        comm_host=comm_host,
        data_port=data_port,
        control_port=control_port,
        status_port=status_port,
    )
