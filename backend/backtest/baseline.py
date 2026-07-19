"""基线回测报告生成器。

ponytail: 0.7.1 起完全走 axon_quant 事件驱动回测 (BacktestEngine + 多 leg API)
         旧版简化回测 (手写仓位状态机) 已删除,统一在引擎层算 PnL / 撮合 / funding
         8 策略模板的基线参考走这里,用于快速 sanity check
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from strategy.loader import StrategyLoader
from axon_bridge import (
    BacktestEngine,
    spot_instrument,
    swap_instrument,
)
from axon_bridge.backtest import PushFundingHelper

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """纳秒精度 ISO 8601 时间戳,符合项目硬约束。"""
    now = datetime.now(timezone.utc)
    micro = now.microsecond * 1000
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{micro:09d}+00:00"


def make_synthetic_kline(
    n: int = 200,
    start_price: float = 30000.0,
    seed: int = 42,
) -> pd.DataFrame:
    """生成合成 K 线 DataFrame(走 GBM 随机游走)。

    ponytail: 仅用于基线/单元测试,避免依赖外部 Parquet
             O(n) 时间 O(n) 空间,n <= 10000 可控
    """
    rng = np.random.default_rng(seed)
    # 日波动率 ~2%,按小时折算 ~0.115%
    sigma = 0.02 / np.sqrt(24)
    drift = 0.0
    rets = rng.normal(drift, sigma, n)
    prices = start_price * np.exp(np.cumsum(rets))
    closes = prices
    opens = np.concatenate([[start_price], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, sigma / 2, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, sigma / 2, n)))
    volumes = rng.uniform(100, 1000, n)
    ts = pd.date_range("2024-07-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


@dataclass
class BaselineReport:
    """基线回测报告数据。"""

    template: str
    symbol: str
    period: str
    interval: str
    candle_type: str
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    total_funding_pnl: float = 0.0  # 0.7.1:funding 累计 PnL(perp short 收 funding)
    report_id: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class BaselineBacktestService:
    """基线回测：加载 K 线 → 跑策略 → 计算 PnL → 写报告。"""

    def __init__(
        self,
        strategy_name: str,
        symbol: str,
        start: str,
        end: str,
        interval: str = "1h",
        candle_type: str = "spot",
        output_dir: Path | None = None,
        data: pd.DataFrame | None = None,
        funding_history_path: str | None = None,
        spot_symbol: str | None = None,
        funding_injection_window_hours: float = 8.0,  # 新增: funding 注入窗口 (小时)
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start = start
        self.end = end
        self.interval = interval
        self.candle_type = candle_type
        self.output_dir = Path(output_dir) if output_dir else Path("data/source/backtest_baselines")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data = data
        self.funding_history_path = funding_history_path
        self.spot_symbol = spot_symbol
        self.funding_injection_window_hours = funding_injection_window_hours  # 新增
        self._funding_history: dict[int, float] | None = None

    def _load_kline(self) -> pd.DataFrame:
        """加载 K 线;外部传入优先(允许空),None 时合成。

        ponytail: data=None → 合成;data=DataFrame(可空)→ 用调用方给的
                 空 DataFrame 由 run() 抛 ValueError
        """
        if self.data is not None:
            return self.data
        # 合成 200 根小时 K 线(约 8 天)够触发所有策略信号
        return make_synthetic_kline(n=200, start_price=30000.0)

    def _load_funding_history(self) -> dict[int, float]:
        """加载 funding 历史 CSV → {funding_time_ms: funding_rate}。

        CSV 格式: funding_time_ms,funding_rate
        路径为空时返回空 dict (兼容老用法)。
        懒加载: 多次调用只解析一次。
        """
        if self._funding_history is not None:
            return self._funding_history
        if not self.funding_history_path:
            self._funding_history = {}
            return self._funding_history
        path = Path(self.funding_history_path)
        if not path.exists():
            # 静默回退, 不报错 (兼容缺数据场景)
            self._funding_history = {}
            return self._funding_history
        history: dict[int, float] = {}
        with path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                history[int(row["funding_time_ms"])] = float(row["funding_rate"])
        self._funding_history = history
        return self._funding_history

    def _compute_funding_periods(
        self, funding_history: dict[int, float]
    ) -> list[tuple[int, int, float]]:
        """把 funding_history dict 展开为 (start_ms, end_ms, rate) periods。

        每个 period 表示 funding 在 [funding_time - window, funding_time] 期间
        内所有 bar 都能拿到这个 rate。用于 funding_injection_window_hours 修复:
        让 funding 8h 期间内的所有 1h bar 都看到 funding_rate, 让策略
        min_hold_bars=8 能在 1h K 线上连续命中 entry。
        """
        if not funding_history:
            return []
        window_ms = int(self.funding_injection_window_hours * 3600 * 1000)
        periods: list[tuple[int, int, float]] = []
        for funding_time_ms, rate in funding_history.items():
            start_ms = funding_time_ms - window_ms
            periods.append((start_ms, funding_time_ms, rate))
        return sorted(periods)

    def _row_timestamp_ms(self, row: pd.Series) -> int:
        """从 row 提取毫秒时间戳。

        ponytail: 优先 'timestamp' 列; 否则用 index name='timestamp' 或 DatetimeIndex
                 老测试 fixture 用 DatetimeIndex (无列), 这里必须兜底
        """
        if "timestamp" in row.index and not isinstance(row["timestamp"], (int, float)):
            try:
                return int(pd.Timestamp(row["timestamp"]).timestamp() * 1000)
            except (ValueError, TypeError):
                pass
        idx_name = row.name
        if isinstance(idx_name, pd.Timestamp):
            return int(idx_name.timestamp() * 1000)
        # 兜底: 0
        return 0

    # axon_quant 0.7.0 默认 8h funding 周期(ns)
    _FUNDING_INTERVAL_NS = 8 * 3600 * 1_000_000_000
    # 虚拟流动性默认 seed 配线: 与 axon_quant 0.7.0 e2e 测试一致
    _SEED_HALF_SPREAD = 0.0005
    _SEED_DEPTH_LEVELS = 3
    _SEED_SIZE_PER_LEVEL = 10.0
    # auto_rebalance 阈值: 0.1% NAV delta
    _AUTO_REBALANCE_THRESHOLD = 0.001

    def run(self) -> BaselineReport:
        """跑基线回测, 返回报告 dataclass。

        0.7.1 改: 完全走 axon_quant BacktestEngine 事件驱动,统一在引擎层
        算 PnL / 撮合 / funding, 不再手写仓位状态机。
        """
        df = self._load_kline()
        if df is None or df.empty:
            raise ValueError(f"K 线数据为空: {self.symbol} {self.interval} {self.start}~{self.end}")

        # 1) 解析 instrument (spot + perp / 单 perp)
        base, quote = self._parse_symbol(self.symbol)
        perp = swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)
        spot = spot_instrument(base, quote) if self.spot_symbol else None

        # 2) 构造 BacktestEngine + 虚拟流动性 + auto_rebalance
        # ponytail: 不链式 (axon_quant 0.7.0 wheel 还没 PR-C chainable 改动)
        #          0.7.1 wheel 发布后可改回链式
        initial_cash = 100_000.0
        engine = BacktestEngine(initial_cash=initial_cash)
        engine.with_seed_liquidity(
            half_spread=self._SEED_HALF_SPREAD,
            depth_levels=self._SEED_DEPTH_LEVELS,
            size_per_level=self._SEED_SIZE_PER_LEVEL,
        )
        engine.with_auto_rebalance(threshold=self._AUTO_REBALANCE_THRESHOLD)

        # 3) funding 历史: 加载 funding_time→rate 映射,在主循环中精确匹配时 push
        #    不依赖 with_funding_schedule (0.7.0 fixed_rate 不会自动 push 事件)
        funding_history = self._load_funding_history()

        # 4) 加载策略
        strategy_cls = StrategyLoader.get(self.strategy_name)
        config = StrategyConfig(name=self.strategy_name, symbol=self.symbol)
        strategy: BaseStrategy = strategy_cls(config)
        ctx = StrategyContext(symbol=self.symbol)
        ctx.spot_target_position = 0.0
        if self.spot_symbol:
            ctx.spot_symbol = self.spot_symbol
        strategy.on_start(ctx)

        # 5) 主循环: 每根 bar → begin_bar → strategy.on_bar → set_target_position
        funding_periods = self._compute_funding_periods(funding_history)
        for _, row in df.iterrows():
            ts_ms = self._row_timestamp_ms(row)
            ts_ns = ts_ms * 1_000_000
            close = float(row["close"])

            # 5a) 构造 bar dict 给 strategy
            bar = {
                "open": float(row.get("open", close)),
                "high": float(row.get("high", close)),
                "low": float(row.get("low", close)),
                "close": close,
                "volume": float(row.get("volume", 0.0)),
                "timestamp": ts_ms,
            }
            bar.setdefault("funding_rate", 0.0)
            bar.setdefault("funding_time", ts_ms)
            bar.setdefault("cross_sectional_rank", 0)

            # 5b) 查 funding_periods: 注入 8h window 内的 funding_rate
            for period_start_ms, period_end_ms, period_rate in funding_periods:
                if period_start_ms <= ts_ms <= period_end_ms:
                    bar["funding_rate"] = period_rate
                    bar["funding_time"] = period_end_ms
                    break

            # 5c) 注入 spot 字段 (单 symbol 模式: spot=perp)
            if self.spot_symbol:
                ctx.spot_close = close
                ctx.spot_volume = float(row.get("volume", 0.0))
            ctx.account_equity = initial_cash  # 简化: 固定 equity, ponytail

            # 5d) 同步 begin_bar (单/多 leg)
            # ponytail: 0.7.0 wheel 还没 PR-A 修复 (begin_bar_multi 接受 list[tuple])
            #          多 leg 场景用连续 2 次 begin_bar workaround
            #          0.7.1 wheel 发布后可改回 begin_bar_multi
            engine.set_clock(ts_ns)
            if spot:
                engine.begin_bar(price=close, instrument=perp)
                engine.begin_bar(price=close, instrument=spot)
            else:
                engine.begin_bar(price=close, instrument=perp)

            # 5e) 策略决策
            action = strategy.on_bar(bar, ctx)

            # 5f) 应用 Action → engine.set_target_position (qty, not pct)
            # strategy.target_position 语义: ratio(占 equity 比例,如 -0.1 = 做空 10% equity)
            # axon_quant target_position 语义: 绝对 qty
            # 转换: qty = ratio * equity / close
            perp_ratio = float(getattr(action, "target_position", 0.0) or 0.0)
            perp_qty = (perp_ratio * ctx.account_equity / close) if close > 0 else 0.0
            engine.set_target_position(perp, perp_qty)
            if spot:
                # spot_target_position 同 perp 语义(ratio)
                spot_ratio = float(getattr(ctx, "spot_target_position", 0.0) or 0.0)
                spot_qty = (spot_ratio * ctx.account_equity / close) if close > 0 else 0.0
                engine.set_target_position(spot, spot_qty)

            # 5f.5) 手动 rebalance: 触发 set_target_position 累积的 leg 实际下单
            # axon_quant 0.7.0 set_target_position 仅设目标,需调 rebalance_to_target
            # 才发市价单。threshold 传 None 沿用 with_auto_rebalance 的配置。
            engine.rebalance_to_target()

            # 5g) funding 推送: 在 rebalance 之后,确保 push_funding
            # 累计时 perp 持仓已建立(否则 funding_pnl=0)。
            # 0.7.0 with_funding_schedule 不会自动 push 事件,需显式 push。
            # ts 用 funding_time(原始资金费率时间) + 1ns 偏移,确保排在
            # 同 bar rebalance fill event 之后被处理。
            # 关键:push_funding 是 queue-based,事件入队后必须立刻 step() 处理,
            # 否则 run() 末尾统一 drain 时 position 已被后续 bar 的 rebalance 清掉,
            # handle_funding 读 position_states=0 → cash_delta=0 → funding_pnl 漏算。
            if funding_history and ts_ms in funding_history:
                rate_at = funding_history[ts_ms]
                engine.push_funding(
                    instrument=perp,
                    funding_rate=rate_at,
                    mark_price=close,
                    timestamp_ns=ts_ns + 1,
                )
                # ponytail:0.7.0 wheel step() 实际可用(单步 dispatch 一个事件),
                # drain 全部 pending 事件,确保 funding_pnl 在持仓未平前结算
                while engine.pending_events > 0:
                    engine.step()

        # 6) 跑完拿 RunResult
        result = engine.run()

        # 7) 从 result 提指标
        total_pnl = result.final_nav - initial_cash
        total_trades = self._count_trades_via_engine(result)
        total_funding_pnl = float(getattr(result, "total_funding_pnl", 0.0) or 0.0)
        max_dd = float(getattr(result, "max_drawdown", 0.0) or 0.0)
        sharpe = self._sharpe_from_bar_nav(getattr(result, "bar_nav_curve", []))

        # 8) win_rate: 从 fills / trades 推 (axon_quant 没直接暴露 win_rate 字段)
        win_rate = self._win_rate_from_trades(result)

        report = BaselineReport(
            template=self.strategy_name,
            symbol=self.symbol,
            period=f"{self.start}~{self.end}",
            interval=self.interval,
            candle_type=self.candle_type,
            total_pnl=round(total_pnl, 4),
            sharpe_ratio=round(sharpe, 4),
            max_drawdown=round(max_dd, 4),
            win_rate=round(win_rate, 4),
            total_trades=total_trades,
            total_funding_pnl=round(total_funding_pnl, 4),
            report_id=str(uuid4()),
            generated_at=_now_iso(),
        )
        self._write_reports(report)
        return report

    @staticmethod
    def _count_trades_via_engine(result) -> int:
        """硬约束 (0.7.1): total_trades = len(result.trades), 不用 result.fills。

        trades 字段是 round-trip 列表(开仓 + 平仓),fills 是每笔成交。
        多 leg 策略同方向同数量 fills 算 1 trade(开 + 平)。
        """
        trades = getattr(result, "trades", None) or []
        return len(trades)

    @staticmethod
    def _sharpe_from_bar_nav(bar_nav_curve) -> float:
        """从 bar_nav_curve 重算 Sharpe (避免 0.7.0 equity_curve 失真)。

        公式: sqrt(periods_per_year) * mean(log_return) / std(log_return)
        默认按 1h bar 算 (periods_per_year = 8760)。
        """
        if not bar_nav_curve or len(bar_nav_curve) < 2:
            return 0.0
        try:
            navs = np.array([float(nav) for _, nav in bar_nav_curve], dtype=float)
            # log return
            log_ret = np.diff(np.log(navs))
            if log_ret.std() <= 0:
                return 0.0
            # 1h bar, periods_per_year = 24 * 365 = 8760
            return float(log_ret.mean() / log_ret.std() * np.sqrt(8760))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _win_rate_from_trades(result) -> float:
        """从 result.trades 算 win_rate (盈利平仓笔数 / 总平仓笔数)。

        TradeRecord 字段: realized_pnl (含费用), 其他 audit 字段
        """
        trades = getattr(result, "trades", None) or []
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if float(getattr(t, "realized_pnl", 0.0)) > 0)
        return wins / len(trades)

    @staticmethod
    def _parse_symbol(symbol: str) -> tuple[str, str]:
        """解析 'BTCUSDT' / 'BTC-USDT' / 'BTCUSDT-PERP' 为 (base, quote)。

        ponytail: 简单规则, 不覆盖所有 symbol 格式; 错误回退到 'BTC'/'USDT'。
        """
        s = symbol.upper().replace("-", "").replace("_", "")
        if s.endswith("PERP"):
            s = s[:-4]
        # 已知 quote 列表
        for q in ("USDT", "USDC", "USD", "BTC", "ETH"):
            if s.endswith(q) and len(s) > len(q):
                return s[: -len(q)], q
        # 兜底
        return "BTC", "USDT"

    def _write_reports(self, report: BaselineReport) -> None:
        base = f"{report.template}_{report.symbol}_{report.period.replace('~', '_')}"
        json_path = self.output_dir / f"{base}.json"
        md_path = self.output_dir / f"{base}.md"
        json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        md_path.write_text(self._render_md(report))

    def _render_md(self, r: BaselineReport) -> str:
        return f"""# {r.template} 基线回测报告

- **模板**: {r.template}
- **标的**: {r.symbol}
- **周期**: {r.period}
- **K线**: {r.interval} ({r.candle_type})
- **报告 ID**: {r.report_id}
- **生成时间**: {r.generated_at}

## 业绩指标

| 指标 | 数值 |
|---|---|
| Total PnL | {r.total_pnl:.4f} |
| Sharpe Ratio | {r.sharpe_ratio:.4f} |
| Max Drawdown | {r.max_drawdown:.4f} |
| Win Rate | {r.win_rate:.2%} |
| Total Trades | {r.total_trades} |

---
*由 QuantCell P1-Sprint 2 BaselineBacktestService 自动生成*
"""
