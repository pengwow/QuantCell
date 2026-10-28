"""paper 成交落库同步器（paper 模式成交不落 DB 的修复）。

paper 泵线程喂 bar → 内核撮合产生的成交只存在于 Rust 引擎内存
（BacktestEngine.bt_state.fills_detail），进程重启即清零，此前 DB 侧无任何
成交记录。这里在泵线程每轮 pump 后经 PaperDriver.fills_since(cursor) 增量
拉取新成交，按 WorkerTrade 契约幂等落库，异常只记日志、不反噬行情泵。

口径（与 worker/live_trade_sync.py 的 LiveTradeSync 对齐）：
- trade_id 拼装 "paper:{worker_id}:{fill_id}:{timestamp_ns}"：fill_id 是
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

ponytail: 游标与 fill→trade_id 索引均为内存态不持久化。天花板：paper 账
纯内存、重启后成交时间线从零重演，历史 DB 记录与新 run 靠 trade_id 幂等
去重、配对行靠 realized_pnl 非空跳过防重写，不做已停 worker 的清理；
升级路径是把运行态 run_id 拼进 trade_id 并在启动时归档旧 run 的记录。
"""

import json
from datetime import datetime

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class PaperTradeSync:
    """经 driver.fills_since / trades_since 游标增量拉取内核成交与配对盈亏，落库到 worker_trades。"""

    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self._cursor = 0
        self._trades_cursor = 0
        # fill_id → trade_id 映射：配对 trade 回填 realized_pnl 时定位
        # finalize fill（最后一根平仓 fill）行。仅覆盖本实例已拉取的区间，
        # 与 fills 游标同寿命（引擎重启则两者一起归零重放，见模块 ponytail 注释）
        self._fill_index: dict[int, str] = {}

    def sync_once(self, driver) -> int:
        """拉取自游标起的新成交与配对盈亏并落库，返回新落库成交笔数。

        仅在 paper 泵线程循环内被调用（调用方已做异常兜底）；单条落库失败
        即中断本轮并保留游标，下轮原样重拉重试（已入库的由 trade_id 查重幂等）。
        """
        from . import crud  # 同包 crud 依赖 models，无环；与 live_trade_sync 口径一致

        inserted = self._sync_fills(driver, crud)
        self._sync_trade_pnl(driver, crud)
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
                    # crud.create_trade_if_not_exists 无法区分「新建」与「查重命中」，
                    # 这里先自查一次：paper 账重启重放会产出同 trade_id 的 fill，
                    # 命中属既有记录，不计入新落库（也不必重复走 crud 提交）
                    exists = (
                        db.query(crud.WorkerTrade).filter(crud.WorkerTrade.trade_id == data["trade_id"]).first()
                        is not None
                    )
                    if not exists:
                        crud.create_trade_if_not_exists(db, data)
                except Exception as e:
                    logger.warning(
                        f"PaperTradeSync: fill_id={data.get('fill_id')} 落库失败 (worker_id={self.worker_id}): {e}"
                    )
                    break
                # 落库成功（含查重命中）才入索引：配对 trade 只会引用 ≤ 当前
                # fills 游标的 fill_id，fail-fast 路径下游标与索引同步停摆
                self._fill_index[fill["fill_id"]] = data["trade_id"]
                inserted += 0 if exists else 1
            else:
                # for 无 break（全部成功）才推进游标；失败路径下轮重拉兜底
                self._cursor += len(fills)

        if inserted:
            logger.info(f"PaperTradeSync: worker_id={self.worker_id} 新落库 {inserted} 笔模拟成交")
        return inserted

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
                    trade_id = self._fill_index.get(finalize_id)
                    if trade_id is None:
                        # finalize fill 不在索引：理论上只可能发生在泵线程
                        # 与 sync 实例寿命错位（引擎重置但游标未归零），跳过
                        # 防脏写，等待重启后重放对齐
                        logger.warning(
                            f"PaperTradeSync: finalize fill_id={finalize_id} 不在索引, "
                            f"跳过配对回填 (worker_id={self.worker_id})"
                        )
                        continue
                    row = db.query(crud.WorkerTrade).filter(crud.WorkerTrade.trade_id == trade_id).first()
                    # paper 账重启重放会重复产出同一配对，已回填即幂等跳过
                    if row is None or row.realized_pnl is not None:
                        continue
                    row.realized_pnl = float(tr["realized_pnl"])
                    row.exit_time = datetime.fromtimestamp(tr["timestamp_ns"] / 1_000_000_000)
                    notional = float(tr["entry_price"]) * abs(float(tr["net_quantity"]))
                    row.realized_pnl_pct = float(tr["realized_pnl"]) / notional * 100 if notional else None
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

    def _to_trade_data(self, fill: dict) -> dict:
        """PaperDriver.fills_since 的 fill dict → WorkerTrade 字段映射（键名严格一致）。"""
        # instrument 是 ("spot", base, quote) / ("swap", base, quote, settle, size)，
        # 统一取前三位拼 DB symbol 口径（与 LiveTradeSync 的 "BASE/QUOTE" 一致）
        inst = fill["instrument"]
        quantity = float(fill["quantity"])
        price = float(fill["price"])

        return {
            "worker_id": self.worker_id,
            "trade_id": f"paper:{self.worker_id}:{fill['fill_id']}:{fill['timestamp_ns']}",
            "symbol": f"{inst[1]}/{inst[2]}",
            "side": str(fill["taker_side"]).lower(),  # 引擎侧 "Buy"/"Sell" → ccxt 口径
            "order_type": "MARKET",  # paper 撮合只产市价单
            "quantity": quantity,
            "price": price,
            "amount": quantity * price,
            "fee": 0.0,
            "fee_currency": "USDT",
            "realized_pnl": None,  # 配对毛盈亏由 _sync_trade_pnl 回填到 finalize 行
            "realized_pnl_pct": None,
            "entry_time": datetime.fromtimestamp(fill["timestamp_ns"] / 1_000_000_000),
            "exit_time": None,
            "raw_data": json.dumps(fill, default=str),
        }
