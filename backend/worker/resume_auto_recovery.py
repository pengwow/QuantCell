"""resume 对账守卫拒绝后的自动恢复（归档重启，以交易所为准）。

设计见 docs/design/2026-11-28-worker-resume-auto-recovery-design.md：
Rust resume_guard 拒绝 →（开关开 & 24h 内未满 3 次）→ best-effort 撤单 →
归档 journal → fresh start（adopt 交易所持仓与现金）。本模块只做决策与
处置编排，驱动线程挂钩见 strategy_manager._driver_live_thread_main；
运行期漂移仍由周期对账兜底（worker.reconciliation.*），本模块不重复其职责。
"""

import json
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 与 Rust live_driver.rs 的 RESUME_GUARD_REJECT_PREFIX 一致（弱契约，Rust
# 侧有测试断言锁定）。Rust 改前缀时两侧必须同步改。
RESUME_GUARD_PREFIX = "恢复守卫拒绝继续交易"

# 频次止损：24h 滑动窗口内满 3 次即停（spec §频次止损）
_WINDOW_S = 24 * 3600
_WINDOW_LIMIT = 3

# 同 worker 可能有多线程并发恢复场景（重启竞态），追加写加进程内锁防行交织。
# ponytail: O_APPEND 单行 <PIPE_BUF 已近似原子，锁只对齐同进程顺序，够用
_ndjson_lock = threading.Lock()


def is_resume_guard_reject(error_message: str) -> bool:
    """识别 Rust resume_guard 拒绝错误（按固定前缀，避免解析中文全文）。"""
    return error_message.startswith(RESUME_GUARD_PREFIX)


def recovery_log_path(worker_id: int) -> Path:
    """频次止损审计文件路径（与 journal 同属 live 目录，但文件独立于归档）。"""
    data_dir = os.environ.get("QUANTCELL_DATA_DIR")
    base = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "data"
    return base / "live" / f"worker_{worker_id}.auto_recovery.ndjson"


def record_recovery(worker_id: int, reconcile_report: dict[str, Any] | None = None) -> None:
    """追加一条自动恢复审计记录（ndjson 一行）。写失败只告警不抛：审计缺失
    不应让 worker 起不来。"""
    path = recovery_log_path(worker_id)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "worker_id": worker_id,
        "verdict": "adopted",
        "reconcile_report": reconcile_report,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _ndjson_lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        logger.warning(f"自动恢复审计写入失败（忽略）: worker_id={worker_id}, error={e}")


def recent_recovery_count(worker_id: int, *, now: float | None = None) -> int:
    """24h 滑动窗口内的自动恢复次数。文件缺失/不可读/坏行一律跳过：审计
    文件只服务于止损计数，任何读异常都不能阻断重启链。"""
    path = recovery_log_path(worker_id)
    if not path.is_file():
        return 0
    now = time.time() if now is None else now
    count = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 坏行容忍：半行写入或手改
                try:
                    ts = datetime.fromisoformat(str(row.get("ts"))).timestamp()
                except ValueError:
                    continue
                if now - ts <= _WINDOW_S:
                    count += 1
    except OSError:
        return 0
    return count
