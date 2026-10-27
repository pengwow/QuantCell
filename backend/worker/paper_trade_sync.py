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
  realized_pnl 无 per-fill 概念，恒 None。

ponytail: 游标内存态不持久化。天花板：paper 账纯内存、重启后成交时间线从
零重演，历史 DB 记录与新 run 靠 trade_id 幂等去重，不做已停 worker 的清理；
升级路径是把运行态 run_id 拼进 trade_id 并在启动时归档旧 run 的记录。
"""

import json
from datetime import datetime

from utils.logger import LogType, get_logger
from utils.db_session import get_db_session

logger = get_logger(__name__, LogType.APPLICATION)


class PaperTradeSync:
    """经 driver.fills_since 游标增量拉取内核成交并幂等落库到 worker_trades。"""

    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self._cursor = 0

    def sync_once(self, driver) -> int:
        """拉取自游标起的新成交并落库，返回新落库笔数（查重跳过不计）。

        仅在 paper 泵线程循环内被调用（调用方已做异常兜底）；单条落库失败
        即中断本轮并保留游标，下轮原样重拉重试（已入库的由 trade_id 查重幂等）。
        """
        from . import crud  # 同包 crud 依赖 models，无环；与 live_trade_sync 口径一致

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
                        db.query(crud.WorkerTrade)
                        .filter(crud.WorkerTrade.trade_id == data["trade_id"])
                        .first()
                        is not None
                    )
                    if not exists:
                        crud.create_trade_if_not_exists(db, data)
                except Exception as e:
                    logger.warning(
                        f"PaperTradeSync: fill_id={data.get('fill_id')} 落库失败 "
                        f"(worker_id={self.worker_id}): {e}"
                    )
                    break
                inserted += 0 if exists else 1
            else:
                # for 无 break（全部成功）才推进游标；失败路径下轮重拉兜底
                self._cursor += len(fills)

        if inserted:
            logger.info(
                f"PaperTradeSync: worker_id={self.worker_id} 新落库 {inserted} 笔模拟成交"
            )
        return inserted

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
            "realized_pnl": None,
            "realized_pnl_pct": None,
            "entry_time": datetime.fromtimestamp(fill["timestamp_ns"] / 1_000_000_000),
            "exit_time": None,
            "raw_data": json.dumps(fill, default=str),
        }
