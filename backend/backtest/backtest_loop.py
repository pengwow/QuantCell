"""BacktestLoop — 使用 axon_quant.backtest.BacktestEngine 的回测循环"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from axon_bridge import (
    BacktestEngine as _NativeBacktestEngine,
)
from axon_bridge import (
    spot_instrument,
    swap_instrument,
)
from strategy.base import BaseStrategy, StrategyContext
from strategy.target import ratio_to_target_qty

logger = logging.getLogger(__name__)

_DEFAULT_HALF_SPREAD_RATIO = 0.0005
_DEFAULT_DEPTH_LEVELS = 5
_DEFAULT_SIZE_PER_LEVEL = 100.0
_DEFAULT_AUTO_REBALANCE_THRESHOLD = 0.001


def clean_ohlcv_df(df: pd.DataFrame) -> pd.DataFrame:
    """清洗 OHLCV DataFrame，保证回测输入按时间单调、无 NaN/Inf。

    承接统一前事件路径 _load_data_to_engine 的数据质量防御：
    列名归一为小写、只保留 OHLCV、timestamp 转 UTC DatetimeIndex、
    排序、重复时间戳保留最后一条、NaN/Inf 填 0。
    """
    required_cols = ["open", "high", "low", "close", "volume"]
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]

    cols_to_keep = [c for c in required_cols if c in out.columns]
    if "timestamp" in out.columns:
        cols_to_keep.insert(0, "timestamp")
    out = out[cols_to_keep]

    if not isinstance(out.index, pd.DatetimeIndex) and "timestamp" in out.columns:
        out = out.set_index("timestamp")
        out.drop(columns=["timestamp"], errors="ignore", inplace=True)

    if len(out) > 0:
        try:
            out.index = pd.to_datetime(out.index, utc=True)
        except Exception:
            out.index = pd.to_datetime(out.index.astype(str), utc=True)

    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]

    for col in required_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
            out[col] = out[col].replace([np.inf, -np.inf], np.nan).astype("float64")
            out[col] = out[col].fillna(0.0)
    return out


@dataclass
class BacktestResult:
    """回测结果"""

    total_pnl: float = 0.0
    total_orders: int = 0
    fills: int = 0
    final_nav: float = 0.0
    max_drawdown: float = 0.0
    orders_accepted: int = 0
    orders_rejected: int = 0
    events_processed: int = 0
    duration_secs: float = 0.0
    total_fees: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    nav_peak: float = 0.0
    max_drawdown_pct: float = 0.0
    trade_records: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    data_start_ns: int = 0
    data_end_ns: int = 0
    bar_count: int = 0
    final_positions: dict = field(default_factory=dict)


class BacktestLoop:
    """唯一回测路径：BaseStrategy (on_bar → Action) → axon_quant BacktestEngine

    Args:
        initial_cash: 初始资金
    """

    def __init__(self, initial_cash: float = 100_000.0):
        self._initial_cash = initial_cash

    def run(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        force_liquidate: bool = False,
        features: dict | None = None,
        feature_dataframe: pd.DataFrame | None = None,
        data_type: str = "kline",
        trading_mode: str = "spot",
        funding_df: pd.DataFrame | None = None,
    ) -> BacktestResult:
        """执行回测

        Args:
            strategy: BaseStrategy 实例（on_bar(bar, ctx) → Action）
            data: OHLCV DataFrame，索引为 DatetimeIndex 或含 timestamp 列
            symbol: 交易对符号
            force_liquidate: 回测结束时是否强制平仓
            features: 特征字典（键值对，注入 StrategyContext）
            feature_dataframe: 特征 DataFrame（序列特征）
            data_type: 数据类型标识
            trading_mode: "spot" 现货 / "futures" 永续（构造 swap 品种并结算资金费）
            funding_df: 资金费率 DataFrame（仅 futures 模式使用）

        Returns:
            BacktestResult
        """
        # 信任边界：清洗归一（单调时间/无 NaN/Inf），后续循环直接依赖
        data = clean_ohlcv_df(data)

        # 从 symbol 如 BTCUSDT 提取 base/quote；futures 用永续品种接资金费结算
        base, quote = self._parse_symbol(symbol)
        instrument = (
            swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)
            if trading_mode == "futures"
            else spot_instrument(base, quote)
        )

        # axon_quant: 链式配置 API
        engine = (
            _NativeBacktestEngine(initial_cash=self._initial_cash)
            .with_seed(42)
            .with_seed_liquidity(
                half_spread=_DEFAULT_HALF_SPREAD_RATIO,
                depth_levels=_DEFAULT_DEPTH_LEVELS,
                size_per_level=_DEFAULT_SIZE_PER_LEVEL,
            )
            .with_auto_rebalance(threshold=_DEFAULT_AUTO_REBALANCE_THRESHOLD)
        )

        if force_liquidate:
            engine = engine.with_force_liquidate(True)

        # futures 资金费率交给引擎，回测内按 funding 时间戳自动结算
        if trading_mode == "futures" and funding_df is not None and not funding_df.empty:
            engine.add_funding_data(instrument, funding_df)

        ctx = StrategyContext(
            symbol=symbol,
            account_equity=self._initial_cash,
            features=features or {},
            feature_dataframe=feature_dataframe,
            data_type=data_type,
        )
        strategy.on_start(ctx)

        # 因子特征查找表：{bar 时间键: 当期因子行}
        # - 回测主路径 data 为 DatetimeIndex（_normalize_dataframe 处理过），bar ts 是纳秒；
        # - 直接调用且 data 带 timestamp 整数列时，bar ts 是原始整数。
        # 特征帧索引为 DatetimeIndex 时按纳秒建键，整数索引时按原值建键，保证精确不错配。
        feature_lookup: dict[int, pd.Series] | None = None
        if feature_dataframe is not None and not feature_dataframe.empty:
            if isinstance(feature_dataframe.index, pd.DatetimeIndex):
                feature_lookup = {
                    int(pd.Timestamp(i).timestamp() * 1_000_000_000): row for i, row in feature_dataframe.iterrows()
                }
            else:
                feature_lookup = {int(i): row for i, row in feature_dataframe.iterrows()}

        total_orders = 0

        # clean_ohlcv_df 已统一小写并只保留 OHLCV(+timestamp)，直接按名取列
        _ts = "timestamp" if "timestamp" in data.columns else None

        for idx, row in data.iterrows():
            # 优先使用 timestamp 列（纳秒时间戳），否则从 DatetimeIndex 转换
            ts = int(row[_ts]) if _ts else int(pd.Timestamp(idx).timestamp() * 1000000000)
            close_price = float(row["close"])

            # axon API: begin_bar(price=, instrument=)
            engine.set_clock(ts)
            engine.begin_bar(price=close_price, instrument=instrument)

            bar = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": close_price,
                "volume": float(row["volume"]),
                "symbol": symbol,
                "timestamp_ns": ts,
            }

            # 更新 ctx 净值 (ponytail: 简化为固定 initial_cash)
            ctx.account_equity = self._initial_cash

            # 逐 bar 注入因子特征（当期快照；NaN 热身值不写入，rank 缺失不写 bar）
            if feature_lookup is not None:
                feat_row = feature_lookup.get(ts)
                if feat_row is not None:
                    ctx.features = {
                        str(k): float(v) for k, v in feat_row.items() if k != "cross_sectional_rank" and pd.notna(v)
                    }
                    rank_v = feat_row.get("cross_sectional_rank")
                    if rank_v is not None and pd.notna(rank_v):
                        bar["cross_sectional_rank"] = int(rank_v)

            # 策略决策（唯一协议：on_bar(bar, ctx) → Action）
            action = strategy.on_bar(bar, ctx)

            # 应用 Action: target_position 是 ratio (占 equity 比例)，
            # 换算为绝对数量；零价 bar（清洗残留）跳过换算保持旧口径
            if str(action.action_type) in ("buy", "sell"):
                ratio = float(getattr(action, "target_position", 0.0) or 0.0)
                qty = ratio_to_target_qty(ratio, self._initial_cash, close_price) if close_price > 0 else 0.0
                engine.set_target_position(instrument, qty)
                # 只统计策略实际发出的买卖决策（剔除 hold bar）
                total_orders += 1

            # 触发调仓 + drain 事件
            engine.rebalance_to_target()
            while engine.pending_events > 0:
                engine.step()

        strategy.on_stop(ctx)

        # 最终结算
        result = engine.run()

        # axon 返回的 max_drawdown_pct 是小数形式（如 0.0023 表示 0.23%）
        # 转换为 USD 绝对值：max_drawdown_usd = nav_peak * drawdown_ratio
        raw_max_dd_pct = float(getattr(result, "max_drawdown_pct", 0.0))
        max_drawdown_usd = result.nav_peak * raw_max_dd_pct
        max_drawdown_pct_display = raw_max_dd_pct * 100.0  # 转换为百分比用于显示
        raw_win_rate = float(getattr(result, "win_rate", 0.0))
        win_rate_display = raw_win_rate * 100.0  # 转换为百分比用于显示
        final_positions = dict(result.positions) if hasattr(result, "positions") else {}

        # 构建 equity_curve: 使用 bar_nav_curve（每根K线一个点），格式适配前端
        equity_curve = []
        bar_nav = list(getattr(result, "bar_nav_curve", []))
        for ts_ns, nav in bar_nav:
            dt = datetime.fromtimestamp(ts_ns / 1e9, tz=UTC)
            dt_str = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            nav_float = float(nav)
            equity_curve.append(
                {
                    # 大写字段（EquityChart 组件支持）
                    "datetime": dt_str,
                    "Equity": nav_float,
                    # 小写兼容字段
                    "equity": nav_float,
                    "formatted_time": dt_str,
                    "timestamp": int(ts_ns / 1e6),  # 毫秒级时间戳
                }
            )

        # 构建 round-trip trades: 从 fills_detail 配对开平仓
        trade_records = self._build_round_trip_trades(list(getattr(result, "fills_detail", [])))

        # 获取数据时间范围：优先使用 timestamp 列
        if "timestamp" in data.columns and len(data) > 0:
            data_start_ns = int(data["timestamp"].iloc[0])
            data_end_ns = int(data["timestamp"].iloc[-1])
        elif len(data) > 0:
            data_start_ns = int(pd.Timestamp(data.index[0]).timestamp() * 1e9)
            data_end_ns = int(pd.Timestamp(data.index[-1]).timestamp() * 1e9)
        else:
            data_start_ns = 0
            data_end_ns = 0

        return BacktestResult(
            total_pnl=result.total_pnl,
            total_orders=total_orders,
            fills=result.fills,
            final_nav=result.final_nav,
            max_drawdown=max_drawdown_usd,
            orders_accepted=result.orders_accepted,
            orders_rejected=result.orders_rejected,
            events_processed=result.events_processed,
            duration_secs=result.duration_secs,
            total_fees=float(getattr(result, "total_fees", 0.0)),
            win_rate=win_rate_display,  # 百分比形式（如 71.43 表示 71.43%）
            sharpe_ratio=float(getattr(result, "sharpe_ratio", 0.0)),
            nav_peak=float(getattr(result, "nav_peak", 0.0)),
            max_drawdown_pct=max_drawdown_pct_display,  # 百分比形式（如 0.23 表示 0.23%）
            trade_records=trade_records,
            equity_curve=equity_curve,
            data_start_ns=data_start_ns,
            data_end_ns=data_end_ns,
            bar_count=len(data),
            final_positions=final_positions,
        )

    @staticmethod
    def _build_round_trip_trades(fills_detail: list[dict]) -> list[dict]:
        """从 fills_detail 配对构建 round-trip trades，兼容大写字段和前端格式。

        ponytail: 简单 FIFO 配对，只处理 Buy→Sell 多头平仓，不支持 short
        """
        if not fills_detail:
            return []

        trades: list[dict] = []
        open_positions: list[dict] = []  # FIFO queue of open buys

        for fill in fills_detail:
            side = fill.get("taker_side", "")
            qty = float(fill.get("quantity", 0.0))
            price = float(fill.get("price", 0.0))
            ts_ns = int(fill.get("timestamp_ns", 0))

            if side == "Buy":
                open_positions.append(
                    {
                        "entry_time_ns": ts_ns,
                        "entry_price": price,
                        "quantity": qty,
                        "remaining": qty,
                    }
                )
            elif side == "Sell" and open_positions:
                # FIFO 配对平仓
                remaining_to_close = qty
                while remaining_to_close > 1e-12 and open_positions:
                    open_pos = open_positions[0]
                    matched_qty = min(open_pos["remaining"], remaining_to_close)

                    entry_dt = datetime.fromtimestamp(open_pos["entry_time_ns"] / 1e9, tz=UTC)
                    exit_dt = datetime.fromtimestamp(ts_ns / 1e9, tz=UTC)
                    pnl = matched_qty * (price - open_pos["entry_price"])
                    entry_value = matched_qty * open_pos["entry_price"]
                    return_pct = (pnl / entry_value * 100.0) if entry_value > 0 else 0.0

                    # 同时提供大写字段（回测表格）和小写字段兼容（其他组件）
                    entry_time_str = entry_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    exit_time_str = exit_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    trades.append(
                        {
                            # 大写字段（前端 types/backtest.ts 中 Trade 接口）
                            "EntryTime": entry_time_str,
                            "ExitTime": exit_time_str,
                            "EntryPrice": open_pos["entry_price"],
                            "ExitPrice": price,
                            "Size": matched_qty,
                            "PnL": pnl,
                            "ReturnPct": return_pct,
                            "Direction": "long",
                            # 小写兼容字段（部分组件可能使用）
                            "entry_time": entry_time_str,
                            "exit_time": exit_time_str,
                            "entry_price": open_pos["entry_price"],
                            "exit_price": price,
                            "size": matched_qty,
                            "pnl": pnl,
                            "return_pct": return_pct,
                            "direction": "long",
                            "side": "sell",
                            "status": "FILLED",
                        }
                    )

                    open_pos["remaining"] -= matched_qty
                    remaining_to_close -= matched_qty
                    if open_pos["remaining"] < 1e-12:
                        open_positions.pop(0)

        return trades

    @staticmethod
    def _parse_symbol(symbol: str) -> tuple[str, str]:
        """解析 'BTCUSDT' / 'BTC-USDT' 为 (base, quote)。"""
        s = symbol.upper().replace("-", "").replace("_", "")
        for q in ("USDT", "USDC", "USD", "BTC", "ETH"):
            if s.endswith(q) and len(s) > len(q):
                return s[: -len(q)], q
        return "BTC", "USDT"
