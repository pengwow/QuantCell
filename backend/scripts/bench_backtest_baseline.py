"""回测基线度量：给多进程作业池提供「串行单进程」对照数据。

用法::

    cd backend && uv run python scripts/bench_backtest_baseline.py --start 2024-01-01 --end 2024-06-30

输出 JSON（stdout 最后一行，便于脚本解析）：
- wall_seconds  墙钟耗时
- cpu_seconds   本进程 CPU 时间
- peak_rss_mb   进程峰值内存
- python_share  cpu_seconds / wall_seconds，越接近 1 说明耗时基本落在 Python 侧
                （含 GIL 绑定段），多进程拆分的收益越直接
"""

import json
import resource
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import typer

# 直接执行脚本时 sys.path[0] 是 scripts/，项目包位于 backend/ 下，先补上再导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 注意：下面的项目包导入必须在 sys.path 注入之后
from backtest.schemas import BacktestConfig
from backtest.service import BacktestService
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.SYSTEM)


def _peak_rss_mb() -> float:
    """峰值内存：ru_maxrss 在 macOS 是字节，在 Linux 是 KB。"""
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor, 1)


def main(
    strategy: str = typer.Option("sma_crossover", help="策略模块名（backend/strategies 下的文件名）"),
    symbol: str = typer.Option("BTC/USDT", help="回测标的"),
    interval: str = typer.Option("1h", help="K 线周期"),
    start: str | None = typer.Option(None, help="开始日期 YYYY-MM-DD，默认 180 天前"),
    end: str | None = typer.Option(None, help="结束日期 YYYY-MM-DD，默认今天"),
    initial_cash: float = typer.Option(100_000.0, help="初始资金"),
    params: str = typer.Option("{}", help="策略参数 JSON，如 '{\"fast\": 10}'"),
) -> None:
    end_date = end or datetime.now().strftime("%Y-%m-%d")
    start_date = start or (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    config = BacktestConfig(
        symbols=[symbol],
        interval=interval,
        start_time=f"{start_date} 00:00:00",
        end_time=f"{end_date} 23:59:59",
        initial_cash=initial_cash,
    )
    service = BacktestService()
    task_id = service.create_task(
        strategy_name=strategy,
        strategy_params=json.loads(params),
        symbols=[symbol],
        timeframes=[interval],
        engine_type=config.engine_type,
        config=config.model_dump(),
    )

    logger.info(f"基线回测开始: {strategy} {symbol} {interval} {start_date} ~ {end_date}")
    wall_started = time.monotonic()
    cpu_started = time.process_time()
    result = service.run_backtest(task_id)
    wall_seconds = round(time.monotonic() - wall_started, 2)
    cpu_seconds = round(time.process_time() - cpu_started, 2)

    metrics = {
        "task_id": str(task_id),
        "strategy": strategy,
        "symbol": symbol,
        "interval": interval,
        "range": f"{start_date} ~ {end_date}",
        "status": result.get("status"),
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "peak_rss_mb": _peak_rss_mb(),
        "python_share": round(cpu_seconds / wall_seconds, 3) if wall_seconds > 0 else None,
    }
    logger.info(f"基线回测完成: {json.dumps(metrics, ensure_ascii=False)}")
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    typer.run(main)
