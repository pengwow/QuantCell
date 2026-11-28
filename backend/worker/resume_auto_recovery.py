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


def should_auto_recover(worker_id: int, *, now: float | None = None) -> tuple[bool, str]:
    """自动恢复总闸：开关 + 频次止损。返回（是否允许，拒绝原因）。

    拒绝原因用于 wlog 交代理由（不是人工确认门——只限制自动化冷却，
    用户仍可手工点「归档并启动」）。
    """
    # 函数内 import 与 strategy_manager 同口径：config_manager 顶层拉
    # collector.db，防 worker.__init__ 循环链在部分入口被点爆
    from utils.config_manager import get_flag

    if not get_flag("worker.resume_auto_recovery.enabled", True):
        return False, "自动恢复开关关闭（worker.resume_auto_recovery.enabled）"
    if recent_recovery_count(worker_id, now=now) >= _WINDOW_LIMIT:
        return False, f"自动恢复止损：24h 内已自动归档重启 {_WINDOW_LIMIT} 次，需人工排查漂移根因"
    return True, ""


def best_effort_cancel_open_orders(trade_sync: Any, wlog: Any) -> None:
    """撤掉该 worker 品种的全部在挂单（best-effort，任何失败不抛出）。

    撤单走 LiveTradeSync 内已构造好的 ccxt 实例（凭证/symbol/连接复用）；
    trade_sync 为 None（LiveTradeSync 构造失败）时整体跳过——归档 adopt 的
    暴露面与人工归档路径相同，撤单只是增强屏障，不构成处置前置条件。
    """
    if trade_sync is None:
        wlog.info("自动恢复撤单跳过：无 trade_sync 成交同步通道")
        return
    ccxt = getattr(getattr(trade_sync, "exchange", None), "exchange", None)
    if ccxt is None:
        wlog.warning("自动恢复撤单跳过：trade_sync 未持有 ccxt 实例")
        return
    symbol = trade_sync.ccxt_symbol
    try:
        orders = ccxt.fetch_open_orders(symbol) or []
    except Exception as e:
        wlog.warning(f"自动恢复撤单失败（继续归档处置）: symbol={symbol}, error={e}")
        return
    for order in orders:
        try:
            ccxt.cancel_order(order.get("id"), symbol)
        except Exception as e:
            wlog.warning(f"自动恢复单笔撤单失败（继续）: symbol={symbol}, order_id={order.get('id')}, error={e}")
    wlog.info(f"自动恢复撤单完成: symbol={symbol}, 处理挂单数={len(orders)}")
