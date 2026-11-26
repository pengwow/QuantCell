"""live 成交落库同步器（B2 修复：live 模式成交不落 DB）。

背景：live 链路的成交回报走 Rust 引擎（journal 只记外部输入，Order/Fill 属
派生事件不落盘，且 VenueUpdate state 缺 symbol/side），因此 Python 侧照抄
LiveTradeRecorder 的 journal 通路无法补齐落库字段。这里改用 ccxt REST
fetch_my_trades 增量轮询交易所成交明细，直接按 WorkerTrade 契约幂等落库，
零 Rust 改动，异常只记日志、不反噬交易循环。

口径（与 worker/event_handler.py 的 LiveTradeRecorder 一致）：
- fill_id 用交易所原生成交 ID，create_trade_if_not_exists 全局查重幂等；
- realized_pnl 取 binance futures myTrades 的 info.realizedPnl，缺失为 None；
- order_type 兜底 "MARKET"（ccxt myTrades 不带原生 orderType 字段）。

成交证据链（P0-01）：每笔回报同时提取 info.clientOrderId / info.orderId 随
WorkerTrade 落库，crud.create_trade_if_not_exists 侧与 worker_fill_evidence
同事务双写（venue_trade_id 幂等主锚）；孤立成交观测走 find_orphan_fill_client_ids。

同步游标（P0-02）：since 游标按 (worker_id, account_id) 持久化到
worker_sync_cursor，进程重启后从上次提交位置续拉，不再漏停机期间成交；
启动回补检查 backfill_from_cursor 负责告警与超长 gap 截断。
"""

import json
import os
from datetime import datetime
from hashlib import sha1

from exchange.binance.exchange import BinanceExchange
from utils.config_manager import get_flag
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger
from worker import ws_fill_events

from .vocab import normalize_position_side, normalize_side

logger = get_logger(__name__, LogType.APPLICATION)

# live 成交轮询间隔（秒）。远低于交易所 rate limit 预算，
# snapshot 推送同模式节流，均挂在驱动线程 tick 循环内。
LIVE_TRADE_SYNC_INTERVAL_S = 10.0

# 同步游标告警/截断阈值：游标落后当前时刻超过 6h 记一次 sync_gap 告警；
# 超过截断阈值（默认 24h）直接截断（放弃更早的成交，避免一次回补拉上万笔
# 拖死驱动线程）。截断阈值支持 env 覆盖（P1-4）：长周期策略希望保留更长
# 断点回补窗口时按毫秒设置 QUANTCELL_CURSOR_TRUNCATE_GAP_MS。
CURSOR_WARN_GAP_MS = 6 * 3600 * 1000
CURSOR_TRUNCATE_GAP_MS = max(
    CURSOR_WARN_GAP_MS,
    int(os.environ.get("QUANTCELL_CURSOR_TRUNCATE_GAP_MS", str(24 * 3600 * 1000))),
)


def account_id_for_key(api_key: str) -> str:
    """API key 的稳定短标识：SHA1 前 8 位。明文 key 不落库，换 key 后游标隔离。"""
    return sha1(api_key.encode()).hexdigest()[:8]


def load_cursor(worker_id: int, account_id: str) -> tuple[int, str | None] | None:
    """读取持久化游标；无记录返回 None（冷启动回退旧行为）。"""
    from .models import WorkerSyncCursor  # 同包 models 顶层无环，与 crud 口径一致

    with get_db_session() as db:
        row = (
            db.query(WorkerSyncCursor)
            .filter(WorkerSyncCursor.worker_id == worker_id, WorkerSyncCursor.account_id == account_id)
            .first()
        )
        if row is None:
            return None
        return int(row.cursor_ts), row.cursor_trade_id


def save_cursor(db, worker_id: int, account_id: str, ts: int, trade_id: str | None) -> None:
    """在同 session 内 upsert 游标（查询-更新/插入，不 commit，由调用方随事务提交）。

    ponytail: 每 worker 一个同步线程，同 (worker_id, account_id) 无并发写，
    查-改-插足够；若将来出现多写者再换 dialect 级 on_conflict_do_update。
    """
    from .models import WorkerSyncCursor

    row = (
        db.query(WorkerSyncCursor)
        .filter(WorkerSyncCursor.worker_id == worker_id, WorkerSyncCursor.account_id == account_id)
        .first()
    )
    if row is None:
        db.add(WorkerSyncCursor(worker_id=worker_id, account_id=account_id, cursor_ts=ts, cursor_trade_id=trade_id))
    else:
        row.cursor_ts = max(int(row.cursor_ts), ts)
        row.cursor_trade_id = trade_id
    db.commit()


def find_orphan_fill_client_ids(worker_id: int, limit: int = 20) -> list[str]:
    """孤立成交观测（P0-01）：evidence 带 client_order_id 但 worker_orders 查无此订单。

    用于驱动线程启动时告警「有成交无订单意图」的异常态（如订单行被清理/手工删除、
    或非本系统下单后被同步进来）。仅观测返回列表，不自动删改。
    """
    from .models import WorkerFillEvidence, WorkerOrder

    with get_db_session() as db:
        rows = (
            db.query(WorkerFillEvidence.client_order_id)
            .outerjoin(WorkerOrder, WorkerOrder.client_order_id == WorkerFillEvidence.client_order_id)
            .filter(
                WorkerFillEvidence.worker_id == worker_id,
                WorkerFillEvidence.client_order_id.isnot(None),
                WorkerOrder.id.is_(None),
            )
            .distinct()
            .limit(limit)
            .all()
        )
    return [r[0] for r in rows]


class LiveTradeSync:
    """按 since 游标增量轮询 fetch_my_trades 并幂等落库到 worker_trades。"""

    def __init__(
        self,
        worker_id: int,
        api_key: str,
        api_secret: str,
        symbol: str,
        testnet: bool = True,
    ):
        """构造轮询器。

        Args:
            worker_id: 落库归属的 worker
            api_key/api_secret: 已由 StrategyManager 从 CredentialsService 取得的凭证
            symbol: 归一化格式 "BTC/USDT"（DB symbol 口径与 LiveTradeRecorder 一致）
            testnet: 与 LiveDriver v1 边界一致，默认 Binance 合约测试网
        """
        self.worker_id = worker_id
        self.symbol = symbol

        # 成交广播信封的 strategy_id：worker↔strategy 绑定运行期不变，
        # 惰性解析一次并缓存（构造期不查库，纯逻辑测试无需 DB 也能构造）
        self._strategy_id_cache: str | None = None

        # v1 边界仅 Binance USDT-M 永续；trading_mode="future" 使 ccxt defaultType
        # 指向 fapi，testnet=True 复用 BinanceExchange 手工覆盖端点的既有逻辑
        self.exchange = BinanceExchange(
            api_key=api_key,
            secret_key=api_secret,
            trading_mode="future",
            testnet=testnet,
        )

        # ccxt swap 市场统一符号带结算后缀："BTC/USDT" → "BTC/USDT:USDT"
        _base, _, quote = symbol.partition("/")
        self._ccxt_symbol = f"{symbol}:{quote}" if ":" not in symbol and quote else symbol

        # 同步游标（P0-02）：开关开启且有持久化游标 → 从上次提交位置续拉；
        # 开关关闭（回退旧行为）或首启无游标 → 起点=构造时刻
        self.account_id = account_id_for_key(api_key)
        self._cursor_enabled = get_flag("worker.execution.sync_cursor_enabled", True)
        cursor = load_cursor(worker_id, self.account_id) if self._cursor_enabled else None
        if cursor:
            self._since = cursor[0]
            logger.info(
                f"LiveTradeSync: worker_id={worker_id} 从持久化游标续拉 "
                f"since={cursor[0]} ({datetime.fromtimestamp(cursor[0] / 1000)})"
            )
        else:
            # 起点取构造时刻（毫秒）：驱动尚未启动，不会有更早的新成交
            self._since = self.exchange.exchange.milliseconds()

    @property
    def ccxt_symbol(self) -> str:
        """ccxt 统一符号（带结算后缀），供周期对账等包内调用方只读访问"""
        return self._ccxt_symbol

    def backfill_from_cursor(self) -> tuple[float, bool, bool]:
        """启动回补检查（P0-02 改造点 C。

        Returns:
            (gap_hours, warned, truncated)：游标落后小时数；是否触发 sync_gap
            告警阈值；是否已截断（截断时 since 被改写并写回游标，避免反复告警）。
        """
        now_ms = self.exchange.exchange.milliseconds()
        gap_ms = now_ms - self._since
        gap_hours = gap_ms / 3600_000.0
        truncated = False
        if gap_ms > CURSOR_TRUNCATE_GAP_MS:
            self._since = now_ms - CURSOR_TRUNCATE_GAP_MS
            truncated = True
            with get_db_session() as db:
                # 截断点立即写回游标，否则每次重启都会重复截断+告警
                save_cursor(db, self.worker_id, self.account_id, self._since, None)
            logger.warning(
                f"LiveTradeSync: worker_id={self.worker_id} 游标落后 {gap_hours:.1f}h，"
                f"截断为最近 {CURSOR_TRUNCATE_GAP_MS / 3600_000:.0f}h 继续"
            )
        return gap_hours, gap_ms > CURSOR_WARN_GAP_MS, truncated

    def sync_once(self) -> int:
        """拉取新增成交并落库，返回新落库笔数（查重跳过不计）。

        仅在驱动线程 tick 循环内被调用（外部调用方已做异常兜底）；
        单笔落库失败即中断本轮：本轮不再推进持久化游标，下轮从该笔重试，
        避免跳单。全部成功才把游标推进到本轮最大时间戳（与成交量同 session）。
        """
        from . import crud  # 同包 crud 依赖 models，无环；与 event_handler 口径一致

        trades = self.exchange.exchange.fetch_my_trades(self._ccxt_symbol, since=self._since)
        if not trades:
            return 0

        inserted = 0
        max_seen_ts: int | None = None
        max_seen_id: str | None = None
        with get_db_session() as db:
            for t in trades:
                if not t.get("id"):
                    continue
                try:
                    data = self._to_trade_data(t)
                    row = crud.create_trade_if_not_exists(db, data)
                except Exception as e:
                    # 保留持久化游标，下轮从该笔重试
                    logger.warning(f"LiveTradeSync: trade {t.get('id')} 落库失败 (worker_id={self.worker_id}): {e}")
                    break
                # 游标推进用已见最大时间戳（不 +1）：同毫秒多笔成交不漏，
                # 重复拉取由 fill_id 查重 + evidence 幂等兜底。查重命中也推进，
                # 否则游标停在旧值，每轮都重拉同一批（幂等但空转）。
                if t.get("timestamp"):
                    ts = int(t["timestamp"])
                    self._since = max(self._since, ts)
                    max_seen_ts = ts
                    max_seen_id = str(t["id"])
                if row is not None:
                    inserted += 1
                    # 订单持久化：live 链路只拉 myTrades（成交回报），下单意图
                    # 事件与 openOrders 均不可见，故以 clientOrderId（缺省退
                    # venue orderId / trade id）落 FILLED 行，让订单列表有成交历史
                    crud.upsert_order_filled_from_fill(
                        db,
                        worker_id=self.worker_id,
                        client_order_id=data.get("client_order_id")
                        or data.get("venue_order_id")
                        or f"live:{self.worker_id}:{t['id']}",
                        symbol=data["symbol"],
                        side=data["side"],
                        order_type=data["order_type"],
                        quantity=data["quantity"],
                        price=data["price"],
                        venue_order_id=data.get("venue_order_id"),
                        filled_at=data["entry_time"],
                        position_side=data["position_side"],
                    )
                    # 新落库的成交同步广播到前端 WebSocket（旁路，失败不影响入账）
                    ws_fill_events.broadcast_strategy_fill(
                        worker_id=str(self.worker_id),
                        strategy_id=self._strategy_id(),
                        # ccxt trade 的 symbol 为永续口径 "BTC/USDT:USDT"，广播侧统一归一
                        symbol=str(t.get("symbol") or ""),
                        side=str(t.get("side") or ""),
                        price=float(t.get("price") or 0.0),
                        quantity=float(t.get("amount") or 0.0),
                        ts=int(t.get("timestamp") or 0),  # ccxt 毫秒
                    )
            else:
                # for 正常跑完（无 break）：同 session 持久化游标；
                # 失败仅记日志（游标滞后只会导致重复拉取，幂等兜底）
                if max_seen_ts is not None and self._cursor_enabled:
                    try:
                        save_cursor(db, self.worker_id, self.account_id, max_seen_ts, max_seen_id)
                    except Exception as e:
                        logger.warning(f"LiveTradeSync: 游标持久化失败 (worker_id={self.worker_id}): {e}")

        if inserted:
            logger.info(
                f"LiveTradeSync: worker_id={self.worker_id} {self.symbol} "
                f"新落库 {inserted} 笔成交（本轮共 {len(trades)} 笔回报）"
            )
        return inserted

    def _strategy_id(self) -> str:
        """worker↔strategy 绑定运行期不变：首次广播前解析一次并缓存。"""
        if self._strategy_id_cache is None:
            self._strategy_id_cache = ws_fill_events.resolve_worker_strategy_id(self.worker_id)
        return self._strategy_id_cache

    def daily_realized_pnl(self) -> float:
        """DB 当日已实现盈亏汇总（B3 风控当日亏损额度的数据源）。

        聚合逻辑已抽到 crud.sum_daily_realized_pnl，风控回灌与
        risk-status 快照共用同一函数，保证口径唯一。realized_pnl 为空
        （现货 / 无盈亏字段）的行按 0 计。"""
        from .crud import sum_daily_realized_pnl  # 函数内 import：方法层只做委托，避免模块加载顺序问题

        return sum_daily_realized_pnl(self.worker_id)

    def _to_trade_data(self, trade: dict) -> dict:
        """ccxt trade → WorkerTrade 字段映射（键名与 worker_trades 严格一致）。"""
        quantity = float(trade.get("amount") or 0.0)
        price = float(trade.get("price") or 0.0)
        fee = trade.get("fee") or {}
        info = trade.get("info") or {}

        realized = None
        raw_pnl = info.get("realizedPnl")
        if raw_pnl:
            try:
                value = float(raw_pnl)
                # 币安 futures 开仓 fill 的 realizedPnl 也返回 "0.00000000"：
                # 0 视为开仓（置 None）。否则 live 全部 fill 的 realized_pnl
                # 都非 NULL，crud.derive_positions_from_trades 的未配对 fill
                # 推导会把持仓排除干净，总览「当前持仓」恒空。
                # ponytail: 恰好 0 盈亏的平仓 fill 会被误判为开仓（少一行 0 盈亏
                # 展示）；区分需 venue 端逐笔方向元数据，不做。
                realized = value or None
            except (TypeError, ValueError):
                realized = None

        entry_time = None
        if trade.get("timestamp"):
            entry_time = datetime.fromtimestamp(int(trade["timestamp"]) / 1000)

        # 订单意图关联（P0-01）：binance myTrades info 带下单上下文，缺失为 None
        client_order_id = str(info.get("clientOrderId") or "") or None
        venue_order_id = str(info.get("orderId") or "") or None

        return {
            "worker_id": self.worker_id,
            "fill_id": str(trade["id"]),
            "symbol": self.symbol,
            "side": normalize_side(trade.get("side") or ""),
            # 回报声明值直取：binance futures myTrades 的 info.positionSide
            # （LONG/SHORT/BOTH 原生大写，归一落库）；现货/字段缺失兜底 both（单向净仓声明）
            "position_side": normalize_position_side(info.get("positionSide") or "both"),
            # ccxt myTrades 不带 reduceOnly（仅订单层有），trade 行恒 False
            "reduce_only": False,
            "order_type": str(trade.get("orderType") or "MARKET").upper(),
            "quantity": quantity,
            "price": price,
            "notional": quantity * price,
            "fee": float(fee.get("cost") or 0.0),
            "fee_currency": str(fee.get("currency") or "USDT"),
            "realized_pnl": realized,
            "realized_pnl_pct": None,
            "entry_time": entry_time,
            "exit_time": None,
            "client_order_id": client_order_id,
            "venue_order_id": venue_order_id,
            "raw_data": json.dumps(info, default=str),
        }
