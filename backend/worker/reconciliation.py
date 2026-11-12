"""执行对账:落盘报告导入 + 运行期周期对账（P1-02）。

resume 对账报告由 Rust LiveDriver 与 journal 同名落盘（kill-restart 常规路径）：
- 失败：``worker_{id}.reconcile.json``（守卫拒绝路径，_resume_attempt 既有的写盘）
- 成功：``worker_{id}.reconcile_last_ok.json``（P1-02 新增）

import_reconcile_reports 把两类文件解析成摘要写入 worker_logs
(source="reconciliation")，供前端"最近对账"卡片与告警消费。

run_periodic_reconcile 在驱动线程内按周期做运行期对账：本地影子账
（driver.snapshot()）vs 交易所三资（build_venue_snapshot 从 ccxt 拼装），调
axon_worker.reconcile 纯函数比对，结果与 resume 报告落盘同一套文件路径。
开关 ``worker.reconciliation.periodic_enabled``（默认关）。
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from axon_quant import worker as axon_worker
from sqlalchemy.orm import Session

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger("worker.reconciliation")

# 交易所侧对账通道（P1-03 扩展），这些字段非空即视为账实不符
_BREAK_FIELDS = (
    "position_breaks",
    "missing_fills",
    "extra_fills",
    "ghost_orders",
    "orphan_local_orders",
    "cash_break",
)

# fill 窗口上限（笔）：since 不传时拉最近 N 笔。窗口取宽的语义是"窗口覆盖型"
# ——venue 集合 ⊇ local seen 集合，绝不产生 extra_fills 误报；
# ponytail: 单 run 成交 >1000 笔时窗口会截短（表现为漏报而非误报），升级路径
# 是按 journal 首条 ts 分页拉取。
_FILLS_WINDOW_LIMIT = 1000

RECONCILE_LOG_SOURCE = "reconciliation"


def report_path_for(journal_dir: str | Path, worker_id: int, ok: bool) -> Path:
    """对账报告路径（与 Rust live_driver.rs 落盘同套命名）。

    journal 为 ``worker_{id}.jsonl``，报告 = journal 名换扩展名：
    ``worker_{id}.reconcile.json``（失败）/ ``worker_{id}.reconcile_last_ok.json``（成功）。
    """
    suffix = "reconcile_last_ok.json" if ok else "reconcile.json"
    return Path(journal_dir) / f"worker_{worker_id}.{suffix}"


def _summarize(report: dict) -> dict:
    """报告摘要：各项 break 数量与整体 clean 判定（口径同 Rust resume 守卫：

    六类 break 全空即放行；frozen_instruments 属预警信息不参与 clean 判定）。
    """
    counts = {}
    for f in _BREAK_FIELDS:
        val = report.get(f)
        # cash_break 是 dict（单条资金差异记录），按"是否存在"计数；
        # 其余是 list，按条目数
        if isinstance(val, dict):
            counts[f] = 1 if val else 0
        else:
            counts[f] = len(val or [])

    return {"ok": all(v == 0 for v in counts.values()), "counts": counts}


def _file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def import_reconcile_reports(worker_id: int, journal_dir: str | Path, *, db: Session | None = None) -> list[dict]:
    """扫描 journal 目录的对账报告并写入 worker_logs。

    与 execution_lock 同约定：外部传 db 则复用其事务，否则自开短会话。
    同一报告（内容 hash 不变）不重复落库，防止周期导入刷屏。

    Returns:
        本次新落库的报告摘要列表（[{file, ok, counts, hash, reported_at}]）。
    """
    from worker import crud  # 与 live_trade_sync 同口径：函数内 import 防 worker.__init__ 循环链

    def _run(session: Session) -> list[dict]:
        latest = next(
            (log for log in crud.get_worker_logs(session, worker_id, limit=20) if log.source == RECONCILE_LOG_SOURCE),
            None,
        )
        imported: list[dict] = []
        for ok_flag in (False, True):
            path = report_path_for(journal_dir, worker_id, ok=ok_flag)
            if not path.is_file():
                continue
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"对账报告解析失败: {path}: {e}")
                continue
            summary = _summarize(report)
            payload = {
                "file": path.name,
                "ok": summary["ok"],
                "counts": summary["counts"],
                "hash": _file_hash(path),
                "reported_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
            message = json.dumps(payload, ensure_ascii=False)
            if latest is not None and latest.message == message:
                continue  # 内容未变：不重复落库
            level = "INFO" if summary["ok"] else "WARNING"
            crud.create_worker_log(session, worker_id, level, message, source=RECONCILE_LOG_SOURCE)
            imported.append(payload)
        return imported

    if db is not None:
        return _run(db)
    with get_db_session() as session:
        return _run(session)


def recent_reconcile_summaries(worker_id: int, limit: int = 5, *, db: Session | None = None) -> list[dict]:
    """读取最近的 reconciliation 日志摘要（新→旧），供 API 端点消费。

    message 为 import_reconcile_reports 写入的 JSON 摘要；历史脏数据解析失败
    时降级返回原文（raw），不丢记录。
    """
    from worker import crud  # 与 import_reconcile_reports 同口径：防 worker.__init__ 循环链

    def _run(session: Session) -> list[dict]:
        out: list[dict] = []
        for log in crud.get_worker_logs(session, worker_id, limit=50):
            if log.source != RECONCILE_LOG_SOURCE:
                continue
            try:
                payload = json.loads(log.message)
            except json.JSONDecodeError:
                payload = {"raw": log.message}
            out.append(
                {
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "level": log.level,
                    **payload,
                }
            )
            if len(out) >= limit:
                break
        return out

    if db is not None:
        return _run(db)
    with get_db_session() as session:
        return _run(session)


def build_venue_snapshot(exchange, ccxt_symbol: str, since_ms: int | None = None) -> dict:
    """从 ccxt 拼装 venue 三资快照，口径对齐 Rust fetch_venue_snapshot（live_driver.rs）：

    - positions：signed 净额、key=BASE/QUOTE（去 :结算后缀）、近零过滤
    - cash：钱包 total − 未实现盈亏（total 含未实现，钱包口径要扣回）
    - fill_ids：窗口内成交 id 集合；since_ms=None 拉最近 N 笔（宁宽勿窄，
      窄窗口会把 local 已见成交误报成 extra_fills）
    """
    raw = exchange.exchange  # BinanceExchange 包装内的 ccxt 实例

    positions: dict[str, float] = {}
    unrealized = 0.0
    for p in raw.fetch_positions([ccxt_symbol]) or []:
        contracts = p.get("contracts") or 0.0
        if not contracts:
            continue
        key = ccxt_symbol.split(":")[0]
        signed = float(contracts) if p.get("side") == "long" else -float(contracts)
        positions[key] = positions.get(key, 0.0) + signed
        unrealized += float(p.get("unrealizedPnl") or 0.0)
    positions = {k: q for k, q in positions.items() if abs(q) > 1e-12}

    balance = raw.fetch_balance()
    settle = ccxt_symbol.partition("/")[2].split(":")[0] or "USDT"
    cash = float((balance.get("total") or {}).get(settle, 0.0)) - unrealized

    if since_ms is None:
        trades = raw.fetch_my_trades(ccxt_symbol, limit=_FILLS_WINDOW_LIMIT) or []
    else:
        trades = raw.fetch_my_trades(ccxt_symbol, since=since_ms, limit=_FILLS_WINDOW_LIMIT) or []
    fill_ids = sorted({str(t["id"]) for t in trades if t.get("id")})

    return {"positions": positions, "cash": cash, "fill_ids": fill_ids}


def run_periodic_reconcile(
    worker_id: int,
    driver,
    exchange,
    ccxt_symbol: str,
    journal_dir: str | Path,
    since_ms: int | None = None,
) -> list[dict]:
    """运行期一次对账：本地影子账 vs 交易所三资，落盘后导入 DB。

    since_ms 传 None 即"最近 N 笔"覆盖窗口（周期对账默认口径，见
    build_venue_snapshot）。异常向上抛，由驱动线程兜底记日志。

    Returns:
        本次新落库的摘要（import_reconcile_reports 返回值）。
    """
    local = driver.snapshot()
    venue = build_venue_snapshot(exchange, ccxt_symbol, since_ms)
    # open_orders_verified=True 时 reconcile 才会比对挂单差集；周期对账未拉
    # 挂单，缺省 False 让引擎跳过该比对（同 worker_3 孤儿单误报的根因规避）
    report = axon_worker.reconcile(local, venue)

    journal = Path(journal_dir)
    journal.mkdir(parents=True, exist_ok=True)
    clean = _summarize(report)["ok"]
    path = report_path_for(journal, worker_id, ok=clean)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return import_reconcile_reports(worker_id, journal)


# ── P1-03 资金费 / 平仓专项对账 ─────────────────────────────────────


def _log_reconcile_summary(session: Session, worker_id: int, payload: dict) -> bool:
    """reconciliation 摘要落库（source=reconciliation），与最新一条内容相同即跳过。

    Returns:
        True = 本次新落库；False = 去重跳过。
    """
    from worker import crud  # 函数内 import 防 worker.__init__ 循环链（同 import_reconcile_reports）

    latest = next(
        (log for log in crud.get_worker_logs(session, worker_id, limit=20) if log.source == RECONCILE_LOG_SOURCE),
        None,
    )
    message = json.dumps(payload, ensure_ascii=False)
    if latest is not None and latest.message == message:
        return False
    level = "INFO" if payload.get("ok") else "WARNING"
    crud.create_worker_log(session, worker_id, level, message, source=RECONCILE_LOG_SOURCE)
    return True


def funding_breaks(
    worker_id: int,
    exchange,
    ccxt_symbol: str,
    since_ms: int,
    local_positions: dict | None = None,
    *,
    db: Session | None = None,
) -> dict:
    """资金费专项对账（P1-03）：交易所 FUNDING_FEE income 逐笔摘要 + 存在性核对。

    现实约束：live 引擎 OMS/journal 没有逐笔资金费簿记（LiveSink 不记账 funding、
    journal 不产 Funding 事件），详设中"vs 本地资金费记录逐笔差额"当前无本地依据，
    落地为可核算的部分：
    - income 逐笔拉取 → 笔数/净额摘要可见，cash_break 出现时可对照归因；
    - venue_absent：窗口内本地有持仓而交易所 income 为空 → break（疑似
      API 权限/记账丢失）。
    ponytail: 逐笔差额核对需 LiveSink 增加 funding 簿记（Rust 改动）后再升级。

    Returns:
        摘要 payload（落库去重后仍返回，供调用方告警判定）。
    """
    if ":" not in ccxt_symbol:
        return {"kind": "funding", "skipped": "spot"}  # 现货无资金费概念，不产生记录

    def _run(session: Session) -> dict:
        rows = exchange.fetch_funding_fees(ccxt_symbol, since_ms)
        net: dict[str, float] = {}
        for r in rows:
            currency = r.get("currency") or "USDT"
            net[currency] = net.get(currency, 0.0) + float(r.get("amount") or 0.0)
        # 单边缺失（详设"差额>0.01 记 break"的 live 现实等价物）
        venue_absent = bool(local_positions) and not rows
        payload = {
            "kind": "funding",
            "ok": not venue_absent,
            "counts": {"venue_absent": 1 if venue_absent else 0},
            "income_count": len(rows),
            "income_net": {k: round(v, 8) for k, v in net.items()},
        }
        _log_reconcile_summary(session, worker_id, payload)
        return payload

    if db is not None:
        return _run(db)
    with get_db_session() as session:
        return _run(session)


def close_consistency(worker_id: int, *, db: Session | None = None) -> dict:
    """平仓专项对账（P1-03）：paper 配对链（round_trip_id）交叉核对，两类 break：

    - closed_without_rt：品种存在 CLOSED 持仓且有成交、却没有任何配对组 →
      成交落库了而 finalize 回填链完全断裂（详设"无配对平仓"）；
    - rt_unfilled_pnl：配对组的 finalize 行（组键尾段与 trade_id 中段一致）
      realized_pnl 仍为 NULL → 组产出但盈亏回填失败（详设"配对后残留"）。
    详设原口径"组内 residual_qty != 0"不落地：引擎反手 fill 不拆分（同一根
    fill 既是旧组 exit 又是新组 entry），组内买卖量平衡恒被反手打破，字面
    核对必误报。
    ponytail: worker_trades 全量扫描，单 worker 成交量大时升级为按 updated_at 窗口。
    """
    from worker.models import WorkerPosition, WorkerTrade  # 函数内 import 防循环链

    def _is_finalize_row(t) -> bool:
        # trade_id = paper:{worker_id}:{fill_id}:{ts_ns}，round_trip_id = rt:{worker_id}:{finalize_id}
        tid = (t.trade_id or "").split(":")
        rid = (t.round_trip_id or "").split(":")
        return len(tid) >= 3 and len(rid) >= 3 and tid[2] == rid[2]

    def _run(session: Session) -> dict:
        trades = (
            session.query(
                WorkerTrade.symbol,
                WorkerTrade.trade_id,
                WorkerTrade.round_trip_id,
                WorkerTrade.realized_pnl,
            )
            .filter(WorkerTrade.worker_id == worker_id)
            .all()
        )
        rt_symbols = {t.symbol for t in trades if t.round_trip_id}
        trade_symbols = {t.symbol for t in trades}
        closed_symbols = {
            row.symbol
            for row in session.query(WorkerPosition.symbol)
            .filter(WorkerPosition.worker_id == worker_id, WorkerPosition.status == "CLOSED")
            .all()
        }
        # 优先核对该品种确实留有成交记录的，纯残留 CLOSED 行不判 break
        broken_closed = sorted(closed_symbols & (trade_symbols - rt_symbols))
        unfinalized = sum(1 for t in trades if t.round_trip_id and t.realized_pnl is None and _is_finalize_row(t))

        counts = {"closed_without_rt": len(broken_closed), "rt_unfilled_pnl": unfinalized}
        payload = {
            "kind": "close",
            "ok": not any(counts.values()),
            "counts": counts,
            "symbols": broken_closed[:10],
        }
        _log_reconcile_summary(session, worker_id, payload)
        return payload

    if db is not None:
        return _run(db)
    with get_db_session() as session:
        return _run(session)


def run_funding_close_reconcile(
    worker_id: int,
    driver,
    exchange,
    ccxt_symbol: str,
    since_ms: int,
    *,
    db: Session | None = None,
) -> list[dict]:
    """P1-03 专项对账一条龙：资金费（须传交易所包装）+ 平仓配对链核对。

    并入 6h 周期对账 tick（resume → funding → close 顺序），异常向上抛由
    驱动线程兜底记日志。

    Returns:
        本次产生（或去重跳过）的摘要 payload 列表。
    """
    local = driver.snapshot()
    out = [
        funding_breaks(worker_id, exchange, ccxt_symbol, since_ms, local_positions=local.positions or {}, db=db),
        close_consistency(worker_id, db=db),
    ]
    return [item for item in out if not item.get("skipped")]
