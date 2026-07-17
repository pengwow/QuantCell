"""基线回测报告生成器。

ponytail: 用 ParquetDataProvider 加载 K 线 + 简单遍历策略 + 计算 PnL
         axon_quant BacktestEngine 全量集成较复杂,P1-Sprint 2 用简化版
         输出 json + md 报告到 data/source/backtest_baselines/

简化版逻辑:
- 加载 K 线 DataFrame (close 列)
- 遍历每根 K 线, 调 strategy.on_bar 获取 Action
- 按 Action 调整 target_position, 计算日 PnL = position * (close_t - close_{t-1})
- 汇总 total_pnl, sharpe, max_drawdown, win_rate, total_trades
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

import pandas as pd

from quality.parquet_provider import ParquetDataProvider
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from strategy.loader import StrategyLoader


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


def _now_iso() -> str:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    micro = now.microsecond * 1000
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{micro:09d}+00:00"


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
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start = start
        self.end = end
        self.interval = interval
        self.candle_type = candle_type
        self.output_dir = Path(output_dir) if output_dir else Path("data/source/backtest_baselines")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> BaselineReport:
        """跑基线回测, 返回报告 dataclass。"""
        # 1. 加载 K 线
        if ParquetDataProvider is None:
            raise RuntimeError(
                "ParquetDataProvider 不可用, 请检查 quality.data_provider 模块"
            )
        provider = ParquetDataProvider()
        df = provider.get_kline_data(
            self.symbol, self.interval, self.candle_type, self.start, self.end
        )
        if df is None or df.empty:
            raise ValueError(f"K 线数据为空: {self.symbol} {self.interval} {self.start}~{self.end}")

        # 2. 加载策略
        strategy_cls = StrategyLoader.get(self.strategy_name)
        config = StrategyConfig(name=self.strategy_name, symbol=self.symbol)
        strategy: BaseStrategy = strategy_cls(config)
        ctx = StrategyContext(symbol=self.symbol)
        strategy.on_start(ctx)

        # 3. 遍历 K 线, 计算 PnL
        position = 0.0
        entry_price = 0.0
        pnl = 0.0
        trade_count = 0
        wins = 0
        equity_curve: list[float] = [0.0]
        closes = df["close"].tolist()

        for i, row in df.iterrows():
            bar = {
                "open": row.get("open", row["close"]),
                "high": row.get("high", row["close"]),
                "low": row.get("low", row["close"]),
                "close": row["close"],
                "volume": row.get("volume", 0.0),
            }
            # 高级模板可能读取 funding/cross_sectional_rank（默认 0）
            bar.setdefault("funding_rate", 0.0)
            bar.setdefault("cross_sectional_rank", 0)

            action = strategy.on_bar(bar, ctx)
            t = str(action.action_type)

            if t == "buy" and position <= 0:
                if position < 0:
                    # 平空
                    pnl += (entry_price - bar["close"]) * abs(position)
                    if bar["close"] < entry_price:
                        wins += 1
                position = float(action.target_position) if action.target_position > 0 else 0.5
                entry_price = bar["close"]
                trade_count += 1
            elif t == "sell" and position >= 0:
                if position > 0:
                    # 平多
                    pnl += (bar["close"] - entry_price) * position
                    if bar["close"] > entry_price:
                        wins += 1
                position = 0.0
                trade_count += 1
            elif t in ("reduce_long", "reduce_short"):
                position = 0.0

            # 持仓 PnL（标记到市场）
            unrealized = (bar["close"] - entry_price) * position if position > 0 else 0.0
            equity_curve.append(pnl + unrealized)

        # 4. 计算指标
        equity_series = pd.Series(equity_curve)
        daily_returns = equity_series.diff().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std() * (365 ** 0.5)) if len(daily_returns) > 1 and daily_returns.std() > 0 else 0.0
        peak = equity_series.cummax()
        drawdown = (equity_series - peak)
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

        # 5. 写报告
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
