"""paper 成交落库同步器（paper 模式成交不落 DB 的修复）。

paper 泵线程喂 bar → 内核撮合产生的成交只存在于 Rust 引擎内存
（BacktestEngine.bt_state.fills_detail），进程重启即清零，此前 DB 侧无任何
成交记录。这里在泵线程每轮 pump 后经 PaperDriver.fills_since(cursor) 增量
拉取新成交，按 WorkerTrade 契约幂等落库，异常只记日志、不反噬行情泵。

口径（与 worker/live_trade_sync.py 的 LiveTradeSync 对齐）：
- fill_id 拼装 "paper:{worker_id}:{fill_id}:{timestamp_ns}"：引擎 fill_id 是
  fills_detail 下标、单次运行内全局唯一；带上 timestamp_ns 后，paper 账
  重启清零从游标 0 重来的重放成交仍指向同一条 DB 记录（查重幂等，不重复插入）；
- quantity 为正数绝对量，方向在 taker_side（Buy/Sell → buy/sell 对齐 ccxt 口径）；
- fee 无法按笔拆出（引擎按费率扣现金，不随 fill 明细回传），恒 0；
- realized_pnl 是 per-fill 无概念的：引擎在完全平仓/反手时才配对出
  round-trip trade（FLAT_TO_FLAT 聚合语义，PaperDriver.trades_since 增量
  可拉）。配对结果的毛盈亏回填到该 round-trip **最后一根平仓 fill** 的行
  （exit_fill_ids 的最大 fill_id），entry fill 行保持 None —— 这样
  SUM(realized_pnl) = 全部 round-trip 毛盈亏、胜率分母 = round-trip 数，
  与 stats_service 的 SQL 聚合口径天然一致；exit_time / realized_pnl_pct
  （基于 entry_price × |net_quantity| 名义本金）一并写入。
  毛口径与 binance myTrades 的 realizedPnl 一致（手续费不挤入盈亏）。

ponytail: 游标与 fill 下标→DB fill_id 索引均为内存态不持久化。天花板：paper 账
纯内存、重启后成交时间线从零重演，历史 DB 记录与新 run 靠 fill_id 幂等
去重、配对行靠 realized_pnl 非空跳过防重写，不做已停 worker 的清理；
升级路径是把运行态 run_id 拼进 fill_id 并在启动时归档旧 run 的记录。
"""

import json
from datetime import datetime

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger
from worker import ws_fill_events

from .vocab import normalize_side

logger = get_logger(__name__, LogType.APPLICATION)


class PaperTradeSync:
    """经 driver.fills_since / trades_since 游标增量拉取内核成交与配对盈亏，落库到 worker_trades。"""

    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self._cursor = 0
        self._trades_cursor = 0
        # 成交广播信封的 strategy_id：worker↔strategy 绑定运行期不变，
        # 惰性解析一次并缓存（与 LiveTradeSync 同口径）
        self._strategy_id_cache: str | None = None
        # 引擎 fill 下标 → DB fill_id（组装串）映射：配对 trade 回填
        # realized_pnl 时定位 finalize fill（最后一根平仓 fill）行。
        # 仅覆盖本实例已拉取的区间，
        # 与 fills 游标同寿命（引擎重启则两者一起归零重放，见模块 ponytail 注释）
        self._fill_index: dict[int, str] = {}

    def sync_once(self, driver) -> int:
        """拉取自游标起的新成交与配对盈亏并落库，返回新落库成交笔数。

        仅在 paper 泵线程循环内被调用（调用方已做异常兜底）；单条落库失败
        即中断本轮并保留游标，下轮原样重拉重试（已入库的由 fill_id 查重幂等）。
        """
        from . import crud  # 同包 crud 依赖 models，无环；与 live_trade_sync 口径一致

        inserted = self._sync_fills(driver, crud)
        self._sync_trade_pnl(driver, crud)
        self._sync_positions(driver, crud)
        return inserted

    # ── 成交明细落库（fills 游标） ─────────────────────────────────

    def _sync_fills(self, driver, crud) -> int:
        fills = driver.fills_since(self._cursor)
        if not fills:
            return 0

        inserted = 0
        with get_db_session() as db:
            for fill in fills:
                data = self._to_trade_data(fill)
                try:
                    # paper 账重启重放会产出同 fill_id 的 fill，
                    # 命中属既有记录，不计入新落库（也不必重复走 crud 提交）
                    exists = (
                        db.query(crud.WorkerTrade).filter(crud.WorkerTrade.fill_id == data["fill_id"]).first()
                        is not None
                    )
                    if not exists:
                        crud.create_trade_if_not_exists(db, data)
                        # 订单持久化：paper 引擎只回传成交不分发订单事件，
                        # 以 taker_order_id（引擎订单 id，同单分笔共享）为
                        # client_order_id 落 FILLED 行；缺失时退回 fill_id
                        taker_id = str(fill.get("taker_order_id") or "")
                        order_key = taker_id or f"fill{fill['fill_id']}"
                        crud.upsert_order_filled_from_fill(
                            db,
                            worker_id=self.worker_id,
                            client_order_id=f"paper:{self.worker_id}:{order_key}",
                            symbol=data["symbol"],
                            side=data["side"],
                            order_type=data["order_type"],
                            quantity=data["quantity"],
                            price=data["price"],
                            filled_at=data["entry_time"],
                            position_side=data["position_side"],
                        )
                except Exception as e:
                    logger.warning(
                        f"PaperTradeSync: fill_id={data.get('fill_id')} 落库失败 (worker_id={self.worker_id}): {e}"
                    )
                    break
                # 落库成功（含查重命中）才入索引：配对 trade 只会引用 ≤ 当前
                # fills 游标的 fill_id，fail-fast 路径下游标与索引同步停摆
                self._fill_index[fill["fill_id"]] = data["fill_id"]
                inserted += 0 if exists else 1
                if not exists:
                    # 新落库的模拟成交同步广播到前端 WebSocket（旁路，失败不影响入账）
                    inst = fill["instrument"]
                    ws_fill_events.broadcast_strategy_fill(
                        worker_id=str(self.worker_id),
                        strategy_id=self._strategy_id(),
                        # instrument 是 ("swap", base, quote, ...) tuple，取 base/quote
                        symbol=f"{inst[1]}/{inst[2]}",
                        side=str(fill.get("taker_side") or ""),  # 引擎侧 "Buy"/"Sell"，广播侧 lower
                        price=float(fill.get("price") or 0.0),
                        quantity=float(fill.get("quantity") or 0.0),
                        ts=int(fill.get("timestamp_ns") or 0) // 1_000_000,  # ns → ms
                    )
            else:
                # for 无 break（全部成功）才推进游标；失败路径下轮重拉兜底
                self._cursor += len(fills)

        if inserted:
            logger.info(f"PaperTradeSync: worker_id={self.worker_id} 新落库 {inserted} 笔模拟成交")
        return inserted

    def _strategy_id(self) -> str:
        """worker↔strategy 绑定运行期不变：首次广播前解析一次并缓存。"""
        if self._strategy_id_cache is None:
            self._strategy_id_cache = ws_fill_events.resolve_worker_strategy_id(self.worker_id)
        return self._strategy_id_cache

    # ── 配对盈亏回填（trades 游标） ───────────────────────────────

    def _sync_trade_pnl(self, driver, crud) -> int:
        """经 driver.trades_since 增量拉配对 round-trip，把毛盈亏回填到 finalize fill 行。

        游标独立于 fills 游标推进：fail-fast 与 fills 同款（异常中断保留游标
        下轮重拉，靠 realized_pnl 非空跳过防重写）。
        """
        trades = driver.trades_since(self._trades_cursor)
        if not trades:
            return 0

        updated = 0
        with get_db_session() as db:
            for tr in trades:
                try:
                    # FLAT_TO_FLAT 聚合下 exit_fill_ids 可能跨多根部分平仓 fill，
                    # 盈亏归属最后一根（触发完全平仓/反手的那根）
                    finalize_id = max(tr["exit_fill_ids"])
                    fill_id = self._fill_index.get(finalize_id)
                    if fill_id is None:
                        # finalize fill 不在索引：理论上只可能发生在泵线程
                        # 与 sync 实例寿命错位（引擎重置但游标未归零），跳过
                        # 防脏写，等待重启后重放对齐
                        logger.warning(
                            f"PaperTradeSync: finalize fill_id={finalize_id} 不在索引, "
                            f"跳过配对回填 (worker_id={self.worker_id})"
                        )
                        continue
                    row = db.query(crud.WorkerTrade).filter(crud.WorkerTrade.fill_id == fill_id).first()
                    # paper 账重启重放会重复产出同一配对，已回填即幂等跳过
                    if row is None or row.realized_pnl is not None:
                        continue
                    row.realized_pnl = float(tr["realized_pnl"])
                    row.exit_time = datetime.fromtimestamp(tr["timestamp_ns"] / 1_000_000_000)
                    notional = float(tr["entry_price"]) * abs(float(tr["net_quantity"]))
                    row.realized_pnl_pct = float(tr["realized_pnl"]) / notional * 100 if notional else None
                    # 组键回填：finalize fill id 唯一定位一个 round-trip，
                    # paper 重启重放产出同一批 fill_id → 组键跨重启稳定、可幂等判重
                    round_trip_id = f"rt:{self.worker_id}:{finalize_id}"
                    row.round_trip_id = round_trip_id
                    # 组员 = entry_fill_ids + exit_fill_ids 去掉 finalize 自己；
                    # 索引只覆盖 ≤ 当前 fills 游标的 fill，理论全命中，缺失的跳过不猜
                    group_fill_ids = [int(x) for x in tr.get("entry_fill_ids") or []] + [
                        int(x) for x in tr.get("exit_fill_ids") or []
                    ]
                    other_fill_ids = [
                        self._fill_index[fid]
                        for fid in group_fill_ids
                        if fid != finalize_id and self._fill_index.get(fid)
                    ]
                    if other_fill_ids:
                        # 只补空组键（is_(None)），不覆盖既有值；与 realized_pnl
                        # 同一 commit，任何异常一起回滚
                        db.query(crud.WorkerTrade).filter(
                            crud.WorkerTrade.fill_id.in_(other_fill_ids),
                            crud.WorkerTrade.round_trip_id.is_(None),
                        ).update({"round_trip_id": round_trip_id}, synchronize_session=False)
                    updated += 1
                except Exception as e:
                    logger.warning(f"PaperTradeSync: 配对盈亏回填失败 (worker_id={self.worker_id}): {e}")
                    break
            else:
                self._trades_cursor += len(trades)
            # 显式提交：get_db_session 退出不自动 commit（fill 落库靠 crud 内部
            # commit，这里的属性修改必须自行提交，否则 session close 即丢失）。
            # break 路径也提交已成功部分，未消费的 trades 下轮重拉、幂等补齐
            db.commit()

        if updated:
            logger.info(f"PaperTradeSync: worker_id={self.worker_id} 回填 {updated} 笔配对盈亏")
        return updated

    def _sync_positions(self, driver, crud) -> int:
        """对账式把引擎 snapshot 持仓落 worker_positions（P1-10 统一持仓口径）。

        此前 paper 持仓只存引擎内存，get_positions 在表空时退化为未配对 fill
        推导（derive_positions_from_trades），与引擎内存口径分裂且受推导天花板
        限制（反手 fill 已配对被排除，新仓 entry 丢失）。现在每轮 pump 后：

        - 引擎 snapshot 的净仓数量是权威（sign 定方向、abs 定数量）；
        - entry_price / current_price / opened_at 等明细从同 symbol 未配对 fill
          推导复用 crud.derive_positions_from_trades（同表推导，不另立算法）；
          反手场景 derive 缺行时退回该 symbol 最后一笔 fill 的成交价；
        - 引擎已无仓的 OPEN 行标 CLOSED 留痕（position_id 稳定，重启重演复用）。

        无变化不写库；异常只记日志不反噬行情泵（与成交落库同款兜底策略）。
        """
        try:
            snap = driver.snapshot()
            positions = snap.get("positions") or {}
        except Exception as e:
            logger.warning(f"PaperTradeSync: 读取引擎持仓 snapshot 失败 (worker_id={self.worker_id}): {e}")
            return 0

        # snapshot 键与 fill symbol 同为 "BASE/QUOTE" 口径（_to_trade_data 同规则归一）
        engine_positions = {str(sym).replace("_", "/"): float(qty or 0.0) for sym, qty in positions.items()}

        written = 0
        try:
            with get_db_session() as db:
                derived = {d["symbol"]: d for d in crud.derive_positions_from_trades(db, self.worker_id)}
                # 行查找不带 status 过滤：position_id 是稳定业务键（paper:{wid}:{symbol}），
                # 引擎重启重演重新持仓时 CLOSED 行要能复活为 OPEN；只查 OPEN 会查不到
                # 已关闭行而走新建分支，UNIQUE(position_id) 冲突导致整轮对账白跑。
                # 同 worker 同 symbol 至多一行（position_id unique），按 symbol 收集安全。
                worker_rows = (
                    db.query(crud.WorkerPosition).filter(crud.WorkerPosition.worker_id == self.worker_id).all()
                )
                rows_by_symbol = {row.symbol: row for row in worker_rows}

                # paper 杠杆取引擎配置（富化列；两平/强平/保证金比率 live 专属，paper 恒 NULL）
                try:
                    _config = crud.get_worker(db, self.worker_id).get_trading_config_dict() or {}
                except Exception:
                    _config = {}
                paper_leverage = _config.get("leverage")

                # 引擎有仓的 symbol：upsert（quantity/方向以引擎为准）
                for symbol, qty in engine_positions.items():
                    if qty == 0.0:
                        continue
                    row = rows_by_symbol.get(symbol)
                    dv = derived.get(symbol) or {}
                    entry_price = float(dv.get("entry_price") or 0.0)
                    current_price = float(dv.get("current_price") or 0.0)
                    if entry_price == 0.0 or abs(dv.get("quantity", 0.0) - abs(qty)) > 1e-12:
                        # derive 缺行（反手）或数量与引擎不一致：entry 退回最后一笔 fill 价
                        last = (
                            db.query(crud.WorkerTrade.price)
                            .filter(crud.WorkerTrade.worker_id == self.worker_id, crud.WorkerTrade.symbol == symbol)
                            .order_by(crud.WorkerTrade.entry_time.desc())
                            .first()
                        )
                        last_price = float(last[0]) if last and last[0] else 0.0
                        entry_price = entry_price or last_price
                        current_price = current_price or last_price

                    if row is not None:
                        # 全字段命中视为无变化：跳过赋值避免 SQLA dirty 触发无谓 UPDATE
                        unchanged = (
                            row.status == "OPEN"
                            and abs(float(row.quantity or 0.0) - abs(qty)) <= 1e-12
                            and abs(float(row.entry_price or 0.0) - entry_price) <= 1e-12
                            and abs(float(row.current_price or 0.0) - current_price) <= 1e-12
                        )
                        if unchanged:
                            continue
                    else:
                        row = crud.WorkerPosition(
                            worker_id=self.worker_id,
                            position_id=f"paper:{self.worker_id}:{symbol}",
                            symbol=symbol,
                        )
                        db.add(row)
                        row.opened_at = None

                    written += 1
                    row.quantity = abs(qty)
                    # 引擎净仓符号推导 long/short（推导合法：源头是引擎权威净仓）
                    row.position_side = "long" if qty > 0 else "short"
                    row.entry_price = entry_price
                    row.current_price = current_price
                    row.unrealized_pnl = (current_price - entry_price) * abs(qty) * (1 if qty > 0 else -1)
                    row.notional = current_price * abs(qty)
                    row.margin_used = 0.0
                    row.leverage = paper_leverage
                    row.status = "OPEN"
                    row.closed_at = None  # CLOSED 复活（重演重新建仓）时清历史关闭时刻
                    if row.opened_at is None:
                        row.opened_at = (
                            datetime.fromisoformat(dv["opened_at"]) if dv.get("opened_at") else datetime.now()
                        )
                    row.updated_at = datetime.now()

                # 引擎已无仓的 OPEN 行：标 CLOSED 留痕
                for symbol, row in rows_by_symbol.items():
                    if engine_positions.get(symbol, 0.0) == 0.0:
                        if row.status != "CLOSED":
                            row.status = "CLOSED"
                            row.quantity = 0.0
                            row.unrealized_pnl = 0.0
                            row.closed_at = datetime.now()
                            row.updated_at = datetime.now()
                            written += 1

                if written:
                    db.commit()
        except Exception as e:
            logger.warning(f"PaperTradeSync: 持仓对账落库失败 (worker_id={self.worker_id}): {e}")
        return written

    def _to_trade_data(self, fill: dict) -> dict:
        """PaperDriver.fills_since 的 fill dict → WorkerTrade 字段映射（键名严格一致）。"""
        # instrument 是 ("spot", base, quote) / ("swap", base, quote, settle, size)，
        # 统一取前三位拼 DB symbol 口径（与 LiveTradeSync 的 "BASE/QUOTE" 一致）
        inst = fill["instrument"]
        quantity = float(fill["quantity"])
        price = float(fill["price"])

        return {
            "worker_id": self.worker_id,
            "fill_id": f"paper:{self.worker_id}:{fill['fill_id']}:{fill['timestamp_ns']}",
            "symbol": f"{inst[1]}/{inst[2]}",
            "side": normalize_side(fill["taker_side"]),  # 引擎侧 "Buy"/"Sell" → ccxt 口径
            # paper 引擎单向净仓：声明值固定 both、无只减仓概念（铁律2 因此处为固定声明而非推导）
            "position_side": "both",
            "reduce_only": False,
            "order_type": "MARKET",  # paper 撮合只产市价单
            "quantity": quantity,
            "price": price,
            "notional": quantity * price,
            "fee": 0.0,
            "fee_currency": "USDT",
            "realized_pnl": None,  # 配对毛盈亏由 _sync_trade_pnl 回填到 finalize 行
            "realized_pnl_pct": None,
            "entry_time": datetime.fromtimestamp(fill["timestamp_ns"] / 1_000_000_000),
            "exit_time": None,
            "raw_data": json.dumps(fill, default=str),
        }
