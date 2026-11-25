"""回测任务执行主体（可跨进程投递的模块级函数）。

原先嵌在 routes.run_backtest 内的线程闭包，迁移到此供两条路径共用：
- 线程路径（进程池未启用）：routes 起 daemon 线程调用
- 进程池路径（jobs.backtest_job）：worker 进程调用

入参全部是 JSON 数据（task_id + 配置字典），不含 Session / 闭包，
保证既能被 pickle 投递，也不会让 worker 进程碰数据库。
"""

from __future__ import annotations

from typing import Any

from backtest.service import BacktestService
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


def run_backtest_task(
    task_id: str,
    strategy_name: str,
    strategy_params: dict[str, Any] | None,
    backtest_config: dict[str, Any],
    progress_tracker: Any,
) -> dict[str, Any]:
    """创建任务文件并执行一次回测。

    create_task 对同一 task_id 幂等覆盖同内容：进程池路径会在投递前先在 API
    进程创建任务文件（让 stop / 重启补偿能立刻看到任务），worker 再调一次也无害。

    Returns:
        dict: 回测结果（status ∈ success/completed/stopped/error）
    """
    service = BacktestService()
    service_task_id = service.create_task(
        strategy_name=strategy_name,
        strategy_params=strategy_params or {},
        symbols=backtest_config.get("symbols", []),
        timeframes=[backtest_config.get("interval", "1h")],
        engine_type=backtest_config.get("engine_type", "default"),
        config=backtest_config,
        task_id=task_id,
    )
    logger.info(f"[任务 {task_id}] 回测任务文件已创建: {service_task_id}")
    return service.run_backtest(task_id=service_task_id, progress_tracker=progress_tracker)
