"""策略 → 账户 → 实盘部署

ponytail: deploy 流程 = 取凭证 + 加载策略 + 启动策略循环
         干跑模式: 不真下单,仅验证凭证 + 策略可加载
         实盘模式: 委托 TradingEngine.start_strategy()
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from credentials.service import CredentialsService
from engine.trading_engine import get_trading_engine
from strategy.base import BaseStrategy, StrategyConfig
from strategy.loader import StrategyLoader


@dataclass
class WorkerHandle:
    """worker 句柄,表示一个运行中的策略实例。"""

    worker_id: UUID
    strategy_name: str
    account_name: str
    symbol: str
    status: str  # running | stopped | error
    engine_strategy_id: str | None = None  # TradingEngine 返回的 sid
    mode: str = "dry_run"
    started_at: float = 0.0


class StrategyDeployer:
    """策略部署器:把策略 + 账户 + 标的 绑成 worker。"""

    def __init__(self, dry_run: bool = True, credentials_db: str | None = None):
        self.dry_run = dry_run
        self.credentials = CredentialsService(db_path=credentials_db) if credentials_db else CredentialsService()
        self._workers: dict[UUID, WorkerHandle] = {}

    def deploy(self, strategy_name: str, account_name: str, symbol: str) -> WorkerHandle:
        """部署策略到指定账户/标的。

        Raises:
            AccountNotFoundError: 账号不存在
            ValueError: 策略名未知
        """
        # 1. 验证凭证存在
        _api_key, _api_secret = self.credentials.get_credential(account_name)

        # 2. 加载策略类
        strategy_cls = StrategyLoader.get(strategy_name)
        config = StrategyConfig(name=strategy_name, symbol=symbol)
        strategy: BaseStrategy = strategy_cls(config)

        worker_id = uuid4()
        mode = "dry_run" if self.dry_run else "paper"  # 默认 paper，后续可扩展 live

        # 3. 干跑模式: 仅记录, 不真接入 TradingEngine
        if self.dry_run:
            handle = WorkerHandle(
                worker_id=worker_id,
                strategy_name=strategy_name,
                account_name=account_name,
                symbol=symbol,
                status="running",
                engine_strategy_id=None,
                mode="dry_run",
                started_at=time.monotonic(),
            )
            self._workers[worker_id] = handle
            return handle

        # 4. 实盘/paper 模式: 委托 TradingEngine
        engine = get_trading_engine()
        sid = engine.start_strategy(
            strategy=strategy,
            symbols=[symbol],
            strategy_name=strategy_name,
            mode=mode,
        )

        handle = WorkerHandle(
            worker_id=worker_id,
            strategy_name=strategy_name,
            account_name=account_name,
            symbol=symbol,
            status="running",
            engine_strategy_id=sid,
            mode=mode,
            started_at=time.monotonic(),
        )
        self._workers[worker_id] = handle
        return handle

    def stop(self, handle: WorkerHandle) -> None:
        """停止 worker。"""
        if handle.engine_strategy_id:
            engine = get_trading_engine()
            engine.stop_strategy(handle.engine_strategy_id)
        if handle.worker_id in self._workers:
            handle.status = "stopped"

    def list_active(self) -> list[WorkerHandle]:
        """列出所有 running 状态 worker。"""
        return [h for h in self._workers.values() if h.status == "running"]
