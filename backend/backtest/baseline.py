"""基线回测报告生成器。

ponytail: 简化版基线回测 — 不走 axon_quant 事件循环
         加载 K 线 DataFrame → 遍历调 on_bar → 累计 PnL → 写 json + md
         真实集成 axon_quant BacktestEngine 见 backtest/backtest_loop.py
         8 策略模板的基线参考走这里,用于快速 sanity check
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from strategy.loader import StrategyLoader


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
    report_id: str
    generated_at: str

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
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start = start
        self.end = end
        self.interval = interval
        self.candle_type = candle_type
        self.output_dir = Path(output_dir) if output_dir else Path("data/source/backtest_baselines")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # ponytail: data 可选,None 时生成合成 K 线,避免依赖外部 Parquet
        self.data = data

    def _load_kline(self) -> pd.DataFrame:
        """加载 K 线;外部传入优先(允许空),None 时合成。

        ponytail: data=None → 合成;data=DataFrame(可空)→ 用调用方给的
                 空 DataFrame 由 run() 抛 ValueError
        """
        if self.data is not None:
            return self.data
        # 合成 200 根小时 K 线(约 8 天)够触发所有策略信号
        return make_synthetic_kline(n=200, start_price=30000.0)

    def run(self) -> BaselineReport:
        """跑基线回测, 返回报告 dataclass。"""
        df = self._load_kline()
        if df is None or df.empty:
            raise ValueError(f"K 线数据为空: {self.symbol} {self.interval} {self.start}~{self.end}")

        strategy_cls = StrategyLoader.get(self.strategy_name)
        config = StrategyConfig(name=self.strategy_name, symbol=self.symbol)
        strategy: BaseStrategy = strategy_cls(config)
        ctx = StrategyContext(symbol=self.symbol)
        strategy.on_start(ctx)

        position = 0.0
        entry_price = 0.0
        pnl = 0.0
        trade_count = 0
        wins = 0
        equity_curve: list[float] = [0.0]

        for _, row in df.iterrows():
            bar = {
                "open": float(row.get("open", row["close"])),
                "high": float(row.get("high", row["close"])),
                "low": float(row.get("low", row["close"])),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
            }
            # 高级模板可能读取 funding/cross_sectional_rank(默认 0)
            bar.setdefault("funding_rate", 0.0)
            bar.setdefault("cross_sectional_rank", 0)

            action = strategy.on_bar(bar, ctx)
            t = str(action.action_type)

            if t == "buy" and position <= 0:
                if position < 0:
                    pnl += (entry_price - bar["close"]) * abs(position)
                    if bar["close"] < entry_price:
                        wins += 1
                position = float(action.target_position) if action.target_position > 0 else 0.5
                entry_price = bar["close"]
                trade_count += 1
            elif t == "sell" and position >= 0:
                if position > 0:
                    pnl += (bar["close"] - entry_price) * position
                    if bar["close"] > entry_price:
                        wins += 1
                position = 0.0
                trade_count += 1
            elif t in ("reduce_long", "reduce_short"):
                position = 0.0

            # 持仓 PnL(标记到市场)
            unrealized = (bar["close"] - entry_price) * position if position > 0 else 0.0
            equity_curve.append(pnl + unrealized)

        # 计算指标
        equity_series = pd.Series(equity_curve, dtype=float)
        daily_returns = equity_series.diff().dropna()
        if len(daily_returns) > 1 and daily_returns.std() and daily_returns.std() > 0:
            sharpe = float(daily_returns.mean() / daily_returns.std() * np.sqrt(365))
        else:
            sharpe = 0.0
        peak = equity_series.cummax()
        drawdown = equity_series - peak
        max_dd = float(drawdown.min()) if not drawdown.empty else 0.0
        win_rate = (wins / trade_count) if trade_count > 0 else 0.0

        report = BaselineReport(
            template=self.strategy_name,
            symbol=self.symbol,
            period=f"{self.start}~{self.end}",
            interval=self.interval,
            candle_type=self.candle_type,
            total_pnl=round(pnl, 4),
            sharpe_ratio=round(sharpe, 4),
            max_drawdown=round(max_dd, 4),
            win_rate=round(win_rate, 4),
            total_trades=trade_count,
            report_id=str(uuid4()),
            generated_at=_now_iso(),
        )
        self._write_reports(report)
        return report

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
