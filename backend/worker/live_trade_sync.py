"""live 成交落库同步器（B2 修复：live 模式成交不落 DB）。

背景：live 链路的成交回报走 Rust 引擎（journal 只记外部输入，Order/Fill 属
派生事件不落盘，且 VenueUpdate state 缺 symbol/side），因此 Python 侧照抄
LiveTradeRecorder 的 journal 通路无法补齐落库字段。这里改用 ccxt REST
fetch_my_trades 增量轮询交易所成交明细，直接按 WorkerTrade 契约幂等落库，
零 Rust 改动，异常只记日志、不反噬交易循环。

口径（与 worker/event_handler.py 的 LiveTradeRecorder 一致）：
- trade_id 用交易所原生成交 ID，create_trade_if_not_exists 全局查重幂等；
- realized_pnl 取 binance futures myTrades 的 info.realizedPnl，缺失为 None；
- order_type 兜底 "MARKET"（ccxt myTrades 不带原生 orderType 字段）。

ponytail: 游标不做持久化，起点=同步器构造时刻。天花板：进程在两轮轮询之间
崩溃（默认 10s 窗口）可能漏记窗口内成交，重启后不会自动补捞历史；升级路径是
把 since 持久化到 worker 运行态并在启动时读回。
"""

import json
from datetime import datetime

from exchange.binance.exchange import BinanceExchange
from utils.logger import LogType, get_logger
from utils.db_session import get_db_session

logger = get_logger(__name__, LogType.APPLICATION)

# live 成交轮询间隔（秒）。远低于交易所 rate limit 预算，
# snapshot 推送同模式节流，均挂在驱动线程 tick 循环内。
LIVE_TRADE_SYNC_INTERVAL_S = 10.0


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

        # v1 边界仅 Binance USDT-M 永续；trading_mode="future" 使 ccxt defaultType
        # 指向 fapi，testnet=True 复用 BinanceExchange 手工覆盖端点的既有逻辑
        self.exchange = BinanceExchange(
            api_key=api_key,
            secret_key=api_secret,
            trading_mode="future",
            testnet=testnet,
        )

        # ccxt swap 市场统一符号带结算后缀："BTC/USDT" → "BTC/USDT:USDT"
        base, _, quote = symbol.partition("/")
        self._ccxt_symbol = f"{symbol}:{quote}" if ":" not in symbol and quote else symbol

        # 起点取构造时刻（毫秒）：驱动尚未启动，不会有更早的新成交
        self._since = self.exchange.exchange.milliseconds()

    def sync_once(self) -> int:
        """拉取新增成交并落库，返回新落库笔数（查重跳过不计）。

        仅在驱动线程 tick 循环内被调用（外部调用方已做异常兜底）；
        单笔落库失败即中断本轮并保留游标，下轮从该笔重试，避免跳单。
        """
        from . import crud  # 同包 crud 依赖 models，无环；与 event_handler 口径一致

        trades = self.exchange.exchange.fetch_my_trades(self._ccxt_symbol, since=self._since)
        if not trades:
            return 0

        inserted = 0
        with get_db_session() as db:
            for t in trades:
                if not t.get("id"):
                    continue
                try:
                    crud.create_trade_if_not_exists(db, self._to_trade_data(t))
                except Exception as e:
                    # 保留游标，下轮从该笔重试
                    logger.warning(
                        f"LiveTradeSync: trade {t.get('id')} 落库失败 "
                        f"(worker_id={self.worker_id}): {e}"
                    )
                    break
                inserted += 1
                # 游标推进用已见最大时间戳（不 +1）：同毫秒多笔成交不漏，
                # 重复拉取由 trade_id 查重幂等兜底
                if t.get("timestamp"):
                    self._since = max(self._since, int(t["timestamp"]))

        if inserted:
            logger.info(
                f"LiveTradeSync: worker_id={self.worker_id} {self.symbol} "
                f"新落库 {inserted} 笔成交（本轮共 {len(trades)} 笔回报）"
            )
        return inserted

    def _to_trade_data(self, trade: dict) -> dict:
        """ccxt trade → WorkerTrade 字段映射（键名与 worker_trades 严格一致）。"""
        quantity = float(trade.get("amount") or 0.0)
        price = float(trade.get("price") or 0.0)
        fee = trade.get("fee") or {}

        realized = None
        raw_pnl = (trade.get("info") or {}).get("realizedPnl")
        if raw_pnl:
            try:
                realized = float(raw_pnl)
            except (TypeError, ValueError):
                realized = None

        entry_time = None
        if trade.get("timestamp"):
            entry_time = datetime.fromtimestamp(int(trade["timestamp"]) / 1000)

        return {
            "worker_id": self.worker_id,
            "trade_id": str(trade["id"]),
            "symbol": self.symbol,
            "side": str(trade.get("side") or ""),
            "order_type": str(trade.get("orderType") or "MARKET").upper(),
            "quantity": quantity,
            "price": price,
            "amount": quantity * price,
            "fee": float(fee.get("cost") or 0.0),
            "fee_currency": str(fee.get("currency") or "USDT"),
            "realized_pnl": realized,
            "realized_pnl_pct": None,
            "entry_time": entry_time,
            "exit_time": None,
            "raw_data": json.dumps(trade.get("info") or {}, default=str),
        }
