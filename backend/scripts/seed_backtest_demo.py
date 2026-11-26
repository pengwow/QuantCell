#!/usr/bin/env python3
"""回测中心演示数据播种：归档旧数据 + 用真实引擎跑出真实回测任务。

用途
----
1. ``--clean``：把 ``data/backtest_tasks/task_*.json``、``data/backtest_results/result_*.json``
   及录制/图表等派生文件 **移动**（不 rm）到 ``data/_trash_backtest_<YYYYmmdd_HHMMSS>/``，
   迁移前先把对应 DB ``backtest_tasks`` 行导出到同目录 ``backtest_tasks_db_backup.json``，
   再删除这些 DB 行。
2. ``--seed``：按下方矩阵逐一调用现有 ``BacktestService.create_task`` + ``run_backtest``
   跑真实回测（真实本地 parquet K 线），禁止手写假指标；跑完把任务文件/DB 行的
   创建时间错开到近 12 天内，方便列表页演示。
3. 不带参数：只打印帮助与将要执行的动作（dry-run），不做任何写操作。

用法
----
    cd backend && .venv/bin/python scripts/seed_backtest_demo.py            # dry-run
    cd backend && .venv/bin/python scripts/seed_backtest_demo.py --clean    # 归档旧数据
    cd backend && .venv/bin/python scripts/seed_backtest_demo.py --seed     # 播种
    cd backend && .venv/bin/python scripts/seed_backtest_demo.py --clean --seed --force

幂等
----
``data/backtest_tasks/.seed_demo.json`` 是播种清单（同时任务文件写 ``seed_demo: true``）。
清单存在时 ``--seed`` 默认跳过；``--force`` 会先把清单里的旧任务/结果归档到新的
trash 目录（含 DB 行备份）再重播。

ponytail: 固定矩阵 + 串行执行，不做并发/断点续跑。矩阵是演示场景，不是通用播种框架；
          需要变体时直接改 ``SEED_MATRIX``。自动下载数据的行为被禁用（见
          ``_SeedBacktestService._ensure_kline_data``），数据范围先由预检保证。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 直接执行脚本时 sys.path[0] 是 scripts/，项目包位于 backend/ 下，先补上再导入
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

DATA_DIR = BACKEND / "data"
TASKS_DIR = DATA_DIR / "backtest_tasks"
RESULTS_DIR = DATA_DIR / "backtest_results"
REPLAY_DIR = DATA_DIR / "decision_replay"
CHART_FILE = DATA_DIR / "backtest_chart.png"
MANIFEST = TASKS_DIR / ".seed_demo.json"

INITIAL_CASH = 100_000.0
COMMISSION = 0.0005

# 播种矩阵：策略名 = 策略文件 stem（StrategyLoaderService 会按 templates → strategies
# 顺序查找，实际加载到的类可能与同名文件不同，故参数取「两边默认键的并集」，
# 各自只读自己认识的键，多余键无害）。
# ponytail: 区间严格落在本地 spot K 线可用范围内（见 _check_data_range 预检）。
SEED_MATRIX: list[dict] = [
    {
        "strategy": "sma_crossover",
        "params": {"fast": 10, "slow": 30, "trend_ma": 200, "atr_period": 14},
        "symbol": "BTCUSDT",
        "interval": "15m",
        "start": "2025-01-01",
        "end": "2026-11-19",
    },
    {
        "strategy": "sma_crossover",
        "params": {"fast": 10, "slow": 30, "trend_ma": 200, "atr_period": 14},
        "symbol": "BNBUSDT",
        "interval": "1h",
        "start": "2025-11-24",
        "end": "2026-11-22",
    },
    {
        "strategy": "momentum",
        "params": {"bb_period": 20, "bb_std_dev": 2.0, "lookback": 20, "threshold": 0.05},
        "symbol": "ETHUSDT",
        "interval": "15m",
        "start": "2025-01-01",
        "end": "2026-11-19",
    },
    {
        "strategy": "momentum",
        "params": {"bb_period": 20, "bb_std_dev": 2.0, "lookback": 20, "threshold": 0.05},
        "symbol": "BTCUSDT",
        "interval": "1h",
        "start": "2026-07-01",
        "end": "2026-11-07",
    },
    {
        "strategy": "trend_follow",
        "params": {"atr_period": 14, "channel_ma_period": 20, "atr_multiplier": 2.0, "lookback": 20, "atr_mult": 3.0},
        "symbol": "BTCUSDT",
        "interval": "15m",
        "start": "2025-01-01",
        "end": "2026-11-19",
    },
    {
        "strategy": "trend_follow",
        "params": {"atr_period": 14, "channel_ma_period": 20, "atr_multiplier": 2.0, "lookback": 20, "atr_mult": 3.0},
        "symbol": "ETHUSDT",
        "interval": "1h",
        "start": "2026-06-30",
        "end": "2026-11-06",
    },
    {
        # 原 cross_sectional 单标的调度恒 Hold（排名字段只有多品种回测才注入）→ 0 单，
        # 换成 momentum BNB 1h 展示真实成交
        "strategy": "momentum",
        "params": {"bb_period": 20, "bb_std_dev": 2.0, "lookback": 20, "threshold": 0.05},
        "symbol": "BNBUSDT",
        "interval": "1h",
        "start": "2025-11-24",
        "end": "2026-11-22",
    },
    {
        "strategy": "grid",
        # 该区间 BTC 4h close 约 75.6k~84.5k，网格上下界按此量级取
        "params": {"lower": 70000.0, "upper": 86000.0, "levels": 20},
        "symbol": "BTCUSDT",
        "interval": "4h",
        "start": "2026-10-07",
        "end": "2026-11-06",
    },
    {
        "strategy": "grid",
        # cascade_signal 在回测里缺 state.features（sma5_vs_sma20），stub+force_rule 仍恒 Hold
        # → 0 单，改用 ETH 4h 网格；该区间 ETH close 约 2227~2616，上下界按此量级取
        "params": {"lower": 2200.0, "upper": 2650.0, "levels": 20},
        "symbol": "ETHUSDT",
        "interval": "4h",
        "start": "2026-10-07",
        "end": "2026-11-06",
    },
    {
        "strategy": "martingale",
        "params": {"base_position": 0.1, "multiplier": 2.0, "max_multiplier": 4.0, "direction": "long"},
        "symbol": "LTCUSDT",
        "interval": "15m",
        "start": "2026-04-21",
        "end": "2026-11-19",
    },
]

# 真实失败态示例：策略文件只有 ``class TestStrategy: pass``，loader 找不到 BaseStrategy
# 子类会真实抛错。走同一条 create_task + run_backtest 链路，捕获异常后置 failed + error，
# 不写任何伪造指标。
FAILED_JOB: dict = {
    "strategy": "TestStrategy",
    "params": {},
    "symbol": "BTCUSDT",
    "interval": "15m",
    "start": "2026-01-01",
    "end": "2026-02-01",
    "expect": "failed",
}


# ---------------------------------------------------------------- helpers


def _chunks(items: list[str], size: int = 400):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _trash_dir() -> Path:
    """本次迁移目录：data/_trash_backtest_<YYYYmmdd_HHMMSS>/"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"_trash_backtest_{stamp}"
    n = 1
    while path.exists():
        n += 1
        path = DATA_DIR / f"_trash_backtest_{stamp}_{n}"
    return path


def _move(src: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    src.rename(dest_dir / src.name)


def _backup_and_delete_db_rows(ids: set[str], backup_path: Path) -> int:
    """导出并删除 backtest_tasks 行，返回导出条数。"""
    from backtest.models import BacktestTask
    from utils.db_session import get_db_session

    if not ids:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text("[]", encoding="utf-8")
        return 0

    with get_db_session() as db:
        rows = []
        for chunk in _chunks(sorted(ids)):
            rows.extend(db.query(BacktestTask).filter(BacktestTask.id.in_(chunk)).all())
        payload = [row.to_dict() for row in rows]
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        found = [str(row.id) for row in rows]
        for chunk in _chunks(found):
            db.query(BacktestTask).filter(BacktestTask.id.in_(chunk)).delete(synchronize_session=False)
        db.commit()
    return len(payload)


def _collect_clean_targets() -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    tasks = sorted(TASKS_DIR.glob("task_*.json")) if TASKS_DIR.exists() else []
    results = sorted(RESULTS_DIR.glob("result_*.json")) if RESULTS_DIR.exists() else []
    recordings = sorted(REPLAY_DIR.glob("*.jsonl")) if REPLAY_DIR.exists() else []
    charts = []
    if CHART_FILE.is_file():
        charts.append(CHART_FILE)
    if RESULTS_DIR.exists():
        charts.extend(sorted(RESULTS_DIR.glob("*.png")))
    return tasks, results, recordings, charts


def _task_ids_of(files: list[Path]) -> set[str]:
    ids = set()
    for f in files:
        name = f.name
        if name.startswith("task_") and name.endswith(".json"):
            ids.add(name[len("task_") : -len(".json")])
    return ids


def run_clean() -> int:
    tasks, results, recordings, charts = _collect_clean_targets()
    trash = _trash_dir()
    total = len(tasks) + len(results) + len(recordings) + len(charts)
    print(f"[clean] 迁移目标: {trash}")
    print(
        f"[clean] 任务文件 {len(tasks)} 个 / 结果文件 {len(results)} 个 / "
        f"录制 {len(recordings)} 个 / 图表 {len(charts)} 个"
    )
    if total == 0:
        print("[clean] 没有可迁移的文件")
        return 0

    for f in tasks:
        _move(f, trash / "tasks")
    for f in results:
        _move(f, trash / "results")
    for f in recordings:
        _move(f, trash / "recordings")
    for f in charts:
        _move(f, trash / "charts")

    ids = _task_ids_of(tasks)
    exported = _backup_and_delete_db_rows(ids, trash / "backtest_tasks_db_backup.json")
    if MANIFEST.exists():
        _move(MANIFEST, trash)
        print(f"[clean] 播种清单已归档: {MANIFEST.name}")

    print(f"[clean] 已迁移 {total} 个文件；DB 导出并删除 {exported} 行")
    return 0


def _archive_seed_ids(ids: set[str]) -> None:
    """--force 重播前，把清单里的旧播种产物归档（含 DB 行备份）。"""
    if not ids:
        return
    trash = _trash_dir()
    moved = 0
    for task_id in sorted(ids):
        for src, sub in (
            (TASKS_DIR / f"task_{task_id}.json", "tasks"),
            (RESULTS_DIR / f"result_{task_id}.json", "results"),
        ):
            if src.exists():
                _move(src, trash / sub)
                moved += 1
    exported = _backup_and_delete_db_rows(ids, trash / "backtest_tasks_db_backup.json")
    print(f"[force] 旧播种产物已归档到 {trash}（{moved} 个文件 / {exported} 行 DB）")


# ---------------------------------------------------------------- seed


def _job_config(job: dict) -> dict:
    return {
        "symbols": [job["symbol"]],
        "interval": job["interval"],
        "start_time": f"{job['start']} 00:00:00",
        "end_time": f"{job['end']} 23:59:59",
        "initial_cash": INITIAL_CASH,
        "commission": COMMISSION,
        "trading_mode": "spot",
        "market": "spot",
        "capital_mode": "per_symbol",
        "engine_type": "kernel",
        "data_type": "kline",
        # 详情页「回测配置」还原创建时的策略参数（与 /backtest/run 落库口径一致）
        "strategy_params": job["params"],
        "auto_download": False,
    }


def _data_bounds(symbol: str, interval: str) -> tuple[datetime | None, datetime | None]:
    """读 parquet timestamp 列最小/最大值，自动兼容 ns/µs/ms/s 时间戳单位。"""
    from utils import _find_parquet_file
    from utils.data_utils import _infer_ts_scale

    path = _find_parquet_file(symbol, interval, "spot")
    if path is None or not Path(path).is_file():
        return None, None
    import pyarrow.parquet as pq

    values = pq.read_table(path, columns=["timestamp"]).column("timestamp").to_pylist()
    if not values:
        return None, None
    scale = _infer_ts_scale(max(values))
    lo = datetime.fromtimestamp(min(values) / scale, UTC).replace(tzinfo=None)
    hi = datetime.fromtimestamp(max(values) / scale, UTC).replace(tzinfo=None)
    return lo, hi


def _check_data_range(job: dict) -> str | None:
    """区间必须落在本地数据范围内；不满足返回原因，满足返回 None。"""
    lo, hi = _data_bounds(job["symbol"], job["interval"])
    if lo is None:
        return f"缺少本地数据文件: {job['symbol']} {job['interval']}"
    start = datetime.fromisoformat(f"{job['start']} 00:00:00")
    end = datetime.fromisoformat(f"{job['end']} 23:59:59")
    # 日粒度比较：数据末日可能只到当天某根 bar，不苛求 23:59:59 精确覆盖
    if lo.date() > start.date():
        return f"数据起点 {lo:%Y-%m-%d} 晚于回测起点 {start:%Y-%m-%d}"
    if hi.date() < end.date():
        return f"数据终点 {hi:%Y-%m-%d} 早于回测终点 {end:%Y-%m-%d}"
    return None


def _resolve_fallback(job: dict) -> tuple[dict, str | None]:
    """预检策略能否装配；cascade 装配失败时退化为 fallback 任务。"""
    fallback = job.get("fallback")
    if not fallback:
        return job, None
    job = dict(job)
    try:
        from backtest.strategy_loader_service import StrategyLoaderService

        StrategyLoaderService.load_strategy(
            strategy_name=job["strategy"],
            strategy_params=dict(job["params"]),
            instrument_ids=[{"symbol": job["symbol"], "venue": "BINANCE"}],
            bar_types=[job["interval"]],
            run_mode="backtest",
        )
        return job, None
    except Exception as e:
        reason = f"{job['strategy']} 装配失败，退化 {fallback['strategy']}: {e}"
        merged = dict(job, strategy=fallback["strategy"], params=fallback["params"])
        merged.pop("fallback", None)
        return merged, reason


def _write_task_stamp(task_id: str, created: datetime, error: str | None) -> dict:
    """改写任务文件时间戳 / seed_demo 标记，返回任务内容。"""
    path = TASKS_DIR / f"task_{task_id}.json"
    task = json.loads(path.read_text(encoding="utf-8"))
    task["created_at"] = created.isoformat()
    task["updated_at"] = created.isoformat()
    task["seed_demo"] = True
    if error is not None:
        task["status"] = "failed"
        task["error"] = error
    path.write_text(json.dumps(task, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return task


def _upsert_db_row(
    task_id: str,
    strategy_name: str,
    config: dict,
    status: str,
    created: datetime,
    started: datetime,
    completed: datetime | None,
) -> None:
    from backtest.models import BacktestTask
    from utils.db_session import get_db_session

    with get_db_session() as db:
        row = db.query(BacktestTask).filter_by(id=task_id).first()
        if row is None:
            row = BacktestTask(id=task_id)
            db.add(row)
        row.strategy_name = strategy_name
        row.backtest_config = json.dumps(config, ensure_ascii=False, default=str)
        row.status = status
        row.created_at = created
        row.started_at = started
        row.completed_at = completed
        db.commit()


def _load_manifest() -> dict | None:
    if not MANIFEST.is_file():
        return None
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_manifest(entries: list[dict]) -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(
            {"generated_at": datetime.now(UTC).isoformat(), "tasks": entries},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _fmt(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def run_seed(force: bool, with_failed: bool) -> int:
    manifest = _load_manifest()
    if manifest and not force:
        print(f"[seed] 已存在播种清单 {MANIFEST}，跳过（如需重播用 --force）")
        return 0
    if manifest and force:
        _archive_seed_ids({str(t.get("id")) for t in manifest.get("tasks", []) if t.get("id")})

    # 服务子类：禁用 run_backtest 内置的「数据缺失自动下载」，避免联网。
    # 数据覆盖已由 _check_data_range 预检，true 覆盖下无需下载。
    from backtest.service import BacktestService

    class _SeedBacktestService(BacktestService):
        def _ensure_kline_data(self, task_id, task, progress_tracker=None) -> None:
            # ponytail: 不重复检查/下载；范围由脚本预检。真实缺数据时引擎自会报错。
            return

    service = _SeedBacktestService()

    jobs = [dict(j) for j in SEED_MATRIX]
    if with_failed:
        jobs.append(dict(FAILED_JOB))

    # 创建时间锚点：最后一条任务 = 现在前 60 秒，往前每 6 小时错开一条（近 2 天内，
    # 远小于 12 天上限；「每隔几小时一个」）。真实执行耗时另算 started→completed。
    anchor = datetime.now(UTC) - timedelta(seconds=60)
    spacing = timedelta(hours=6)
    n = len(jobs)

    print(f"[seed] 开始播种 {n} 个任务（真实引擎，串行执行）")
    entries: list[dict] = []
    unexpected: list[str] = []

    for idx, raw_job in enumerate(jobs):
        job, fallback_reason = _resolve_fallback(raw_job)
        label = f"{job['strategy']} {job['symbol']} {job['interval']} {job['start']}→{job['end']}"
        print(f"\n[seed] ({idx + 1}/{n}) {label}")
        if fallback_reason:
            print(f"[seed]   {fallback_reason}")

        expect = raw_job.get("expect", "completed")
        range_error = _check_data_range(job)
        if range_error:
            # 预检失败：不跑引擎、不造指标；落一个 failed 任务说明原因
            print(f"[seed]   预检失败: {range_error}")
            task_id = str(uuid.uuid4())
            config = _job_config(job)
            service.create_task(
                strategy_name=job["strategy"],
                strategy_params=job["params"],
                symbols=[job["symbol"]],
                timeframes=[job["interval"]],
                engine_type="kernel",
                config=config,
                task_id=task_id,
            )
            created = anchor - spacing * (n - 1 - idx)
            _write_task_stamp(task_id, created, range_error)
            _upsert_db_row(task_id, job["strategy"], config, "failed", created, created, created)
            entries.append(_manifest_entry(task_id, job, "failed"))
            _save_manifest(entries)
            unexpected.append(label)
            continue

        task_id = str(uuid.uuid4())
        config = _job_config(job)
        service.create_task(
            strategy_name=job["strategy"],
            strategy_params=job["params"],
            symbols=[job["symbol"]],
            timeframes=[job["interval"]],
            engine_type="kernel",
            config=config,
            task_id=task_id,
        )

        started_wall = time.monotonic()
        error: str | None = None
        try:
            service.run_backtest(task_id)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            print(f"[seed]   引擎执行失败: {error}")
        elapsed = max(1.0, time.monotonic() - started_wall)

        created = anchor - spacing * (n - 1 - idx)
        started_at = created + timedelta(seconds=20 + idx * 3)  # 10~60s 内，确定性错开
        completed_at = started_at + timedelta(seconds=elapsed)

        task = _write_task_stamp(task_id, created, error)
        status = task.get("status") or ("failed" if error else "completed")
        _upsert_db_row(task_id, job["strategy"], config, status, created, started_at, completed_at)

        summary = task.get("metrics_summary") or {}
        metrics = summary.get("metrics") or {}
        entry = {
            "id": task_id,
            "strategy_name": task.get("strategy_name"),
            "symbol": job["symbol"],
            "interval": job["interval"],
            "status": status,
            "total_return": summary.get("total_return"),
            "total_trades": metrics.get("total_trades"),
            "elapsed_seconds": round(elapsed, 3),
        }
        entries.append(entry)
        _save_manifest(entries)

        print(
            f"[seed]   id={task_id} status={status} "
            f"total_return={_fmt(entry['total_return'])} total_trades={entry['total_trades']} "
            f"elapsed={entry['elapsed_seconds']}s"
        )
        if status != expect:
            unexpected.append(label)

    print("\n[seed] 结果汇总")
    header = f"{'task_id':38} {'strategy':16} {'symbol':10} {'tf':4} {'status':10} {'total_return':>12} {'trades':>8}"
    print(header)
    print("-" * len(header))
    for e in entries:
        print(
            f"{e['id']:38} {str(e.get('strategy_name'))[:16]:16} {e.get('symbol', ''):10} "
            f"{e.get('interval', ''):4} {e.get('status')!s:10} "
            f"{_fmt(e.get('total_return')):>12} {e.get('total_trades')!s:>8}"
        )

    if unexpected:
        print(f"\n[seed] {len(unexpected)} 个任务状态与预期不符:")
        for label in unexpected:
            print(f"  - {label}")
        return 1
    print("\n[seed] 全部任务按预期完成")
    return 0


def _manifest_entry(task_id: str, job: dict, status: str) -> dict:
    return {
        "id": task_id,
        "strategy_name": job["strategy"],
        "symbol": job["symbol"],
        "interval": job["interval"],
        "status": status,
    }


# ---------------------------------------------------------------- preview


def _preview() -> None:
    tasks, results, recordings, charts = _collect_clean_targets()
    print("\n[dry-run] 未指定动作，不做任何写操作。")
    print(
        f"[dry-run] --clean 将迁移: 任务 {len(tasks)} / 结果 {len(results)} / "
        f"录制 {len(recordings)} / 图表 {len(charts)} → data/_trash_backtest_<时间戳>/"
        f"，并先导出/删除对应 DB 行"
    )
    manifest = _load_manifest()
    if manifest:
        print(f"[dry-run] --seed 将跳过：已存在清单 {MANIFEST}（--force 可重播）")
        return
    print(f"[dry-run] --seed 将用真实引擎串行跑 {len(SEED_MATRIX) + 1} 个任务：")
    for job in [*SEED_MATRIX, FAILED_JOB]:
        print(f"  - {job['strategy']:16} {job['symbol']:9} {job['interval']:4} {job['start']}→{job['end']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="归档旧回测数据并用真实引擎播种真实回测任务（默认 dry-run）",
        epilog="不带 --clean/--seed 时只打印将执行的动作，不做写操作。",
    )
    parser.add_argument(
        "--clean", action="store_true", help="归档旧任务/结果/录制/图表到 data/_trash_backtest_<ts>/，并备份删除 DB 行"
    )
    parser.add_argument("--seed", action="store_true", help="按固定矩阵用真实引擎跑回测任务")
    parser.add_argument("--force", action="store_true", help="已存在播种清单时先归档旧播种产物再重播")
    parser.add_argument(
        "--with-failed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="附带 1 个真实失败任务（TestStrategy 加载失败），默认开启",
    )
    args = parser.parse_args(argv)

    if not args.clean and not args.seed:
        parser.print_help()
        _preview()
        return 0

    code = 0
    if args.clean:
        code |= run_clean()
    if args.seed:
        code |= run_seed(force=args.force, with_failed=args.with_failed)
    return code


if __name__ == "__main__":
    sys.exit(main())
