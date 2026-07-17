"""策略 → 账户 → 实盘部署（干跑模式）。

ponytail: deploy 流程 = 取凭证 + 加载策略 + 启动策略循环
         干跑模式: 不真下单,仅验证凭证 + 策略可加载
         实盘 deploy: 接入 TradingEngine, 留 P2-B 阶段
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from credentials.service import CredentialsService
from credentials.exceptions import AccountNotFoundError
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
        api_key, api_secret = self.credentials.get_credential(account_name)

        # 2. 加载策略类
        strategy_cls = StrategyLoader.get(strategy_name)
        config = StrategyConfig(name=strategy_name, symbol=symbol)
        strategy: BaseStrategy = strategy_cls(config)

        # 3. 启动 worker
        worker_id = uuid4()
        handle = WorkerHandle(
            worker_id=worker_id,
            strategy_name=strategy_name,
            account_name=account_name,
            symbol=symbol,
            status="running",
        )
        self._workers[worker_id] = handle

        # 4. 干跑模式: 仅记录, 不真接入 TradingEngine
        if not self.dry_run:
            # TODO: 接入 TradingEngine.register_strategy + StrategyLoop.start()
            raise NotImplementedError("实盘 deploy 后续 P2-B 阶段接入")

        return handle

    def stop(self, handle: WorkerHandle) -> None:
        """停止 worker。"""
        if handle.worker_id in self._workers:
            handle.status = "stopped"

    def list_active(self) -> list[WorkerHandle]:
        """列出所有 running 状态 worker。"""
        return [h for h in self._workers.values() if h.status == "running"]
