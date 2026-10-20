"""回测派生指标计算 —— 只用已落盘结果字段（trades / equity_curve / 数据时间范围）的纯函数。

背景：``result_formatter_service.format_axon_results`` 曾把 8 项指标写死 0
（平均回撤、年化波动率、SQN、凯利准则、暴露时间、回测天数、平均/最长持仓时间）。
本模块补齐这些「QuantCell 侧数据已足够、无需下沉引擎」的计算，口径与归属判定见
docs/superpowers/specs/2026-10-19-shared-capital-symbol-metrics-design.md §7。

约定：
- 全部函数对空/退化输入返回 0.0，不抛异常（formatter 不应因指标计算失败而崩）
- 百分比口径：返回百分数（如 12.34 表示 12.34%），与结果 JSON 其它指标一致
"""

from __future__ import annotations

import math

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 加密 7×24 的年 bar 数表，与 factor/service.py::FactorService._periods_per_year 同一口径。
# ponytail: 不复用 FactorService 是为避免 formatter 链路引入 factor.service 的 scipy/DB 依赖；
#           一致性由 tests/unit/backtest/test_derived_metrics.py 的对照断言锁住。
_PERIODS_PER_YEAR = {
    "1m": 365 * 24 * 60,
    "5m": 365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "30m": 365 * 24 * 2,
    "1h": 365 * 24,
    "4h": 365 * 6,
    "1d": 365,
}


def periods_per_year(timeframe: str) -> int:
    """时间周期 → 年 bar 数（用于波动率年化）。未知周期按 1h 兜底。"""
    return _PERIODS_PER_YEAR.get(timeframe, 365 * 24)


def _nav_points(equity_curve: list[dict]) -> list[float]:
    """权益曲线 → 净值序列（兼容 equity/Equity 两种键，跳过非有限数值点）。"""
    navs: list[float] = []
    for point in equity_curve or []:
        if not isinstance(point, dict):
            continue
        raw = point.get("equity", point.get("Equity"))
        if isinstance(raw, (int, float)) and math.isfinite(float(raw)):
            navs.append(float(raw))
    return navs


def avg_drawdown_pct(equity_curve: list[dict]) -> float:
    """平均回撤（%）：沿净值曲线逐点算 (峰值 − 净值) / 峰值，取均值。"""
    navs = _nav_points(equity_curve)
    if len(navs) < 2:
        return 0.0
    peak = navs[0]
    drawdowns: list[float] = []
    for nav in navs:
        peak = max(peak, nav)
        if peak > 0:
            drawdowns.append((peak - nav) / peak)
    if not drawdowns:
        return 0.0
    return round(sum(drawdowns) / len(drawdowns) * 100.0, 4)


def annualized_volatility_pct(equity_curve: list[dict], periods: int) -> float:
    """年化波动率（%）：逐 bar log 收益的样本标准差 × sqrt(年 bar 数)。"""
    navs = _nav_points(equity_curve)
    if len(navs) < 3 or periods <= 0:
        return 0.0
    returns = [math.log(navs[i] / navs[i - 1]) for i in range(1, len(navs)) if navs[i] > 0 and navs[i - 1] > 0]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return round(math.sqrt(variance) * math.sqrt(periods) * 100.0, 4)


def _trade_returns(trades: list[dict]) -> list[float]:
    """逐笔收益率（%）：优先取引擎给的 return_pct，缺失时用 pnl / 开仓名义额兜底。"""
    returns: list[float] = []
    for trade in trades or []:
        if not isinstance(trade, dict):
            continue
        value = trade.get("return_pct")
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            entry_value = float(trade.get("entry_price") or 0.0) * float(trade.get("size") or 0.0)
            if entry_value <= 0:
                continue
            value = float(trade.get("pnl") or 0.0) / entry_value * 100.0
        returns.append(float(value))
    return returns


def sqn(trades: list[dict]) -> float:
    """系统质量数 SQN = sqrt(N) × mean(逐笔收益率) / std(逐笔收益率)。"""
    returns = _trade_returns(trades)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    return round(math.sqrt(len(returns)) * mean / math.sqrt(variance), 4)


def kelly_fraction(trades: list[dict]) -> float:
    """凯利建议仓位 f = W − (1−W)/R（W 胜率、R = 平均盈利额 / 平均亏损额），裁剪到 0..1。

    无亏损笔（R 无定义）或全亏时不外推，返回 0.0。
    """
    pnls = [float(t.get("pnl") or 0.0) for t in (trades or []) if isinstance(t, dict)]
    if not pnls:
        return 0.0
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    if not wins or not losses:
        return 0.0
    win_rate = len(wins) / len(pnls)
    payoff = (sum(wins) / len(wins)) / (abs(sum(losses)) / len(losses))
    if payoff <= 0:
        return 0.0
    fraction = win_rate - (1.0 - win_rate) / payoff
    return round(max(0.0, min(1.0, fraction)), 4)


def _merged_span_seconds(trades: list[dict]) -> float:
    """逐笔持仓区间并集的总秒数（重叠区间合并，同一时刻不重复计时）。"""
    spans: list[tuple[float, float]] = []
    for trade in trades or []:
        if not isinstance(trade, dict):
            continue
        start, end = trade.get("timestamp"), trade.get("exit_timestamp")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            spans.append((float(start), float(end)))
    if not spans:
        return 0.0
    spans.sort()
    total = 0.0
    cur_start, cur_end = spans[0]
    for start, end in spans[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    return total + (cur_end - cur_start)


def exposure_time_pct(trades: list[dict], data_start_ns: int, data_end_ns: int) -> float:
    """暴露时间（%）：逐笔持仓区间并集时长 / 回测总时长。"""
    window_seconds = (float(data_end_ns) - float(data_start_ns)) / 1e9
    if window_seconds <= 0:
        return 0.0
    return round(_merged_span_seconds(trades) / window_seconds * 100.0, 4)


def duration_days(data_start_ns: int, data_end_ns: int) -> int:
    """回测天数：数据时间范围（纳秒）→ 天（向下取整）。"""
    delta = float(data_end_ns) - float(data_start_ns)
    return int(delta / 1e9 / 86400) if delta > 0 else 0


def trade_duration_hours(trades: list[dict]) -> tuple[float, float]:
    """(平均持仓时间, 最长持仓时间)（小时）：逐笔 round-trip 的 entry→exit 时长。"""
    hours = [
        (float(t["exit_timestamp"]) - float(t["timestamp"])) / 3600.0
        for t in (trades or [])
        if isinstance(t, dict)
        and isinstance(t.get("timestamp"), (int, float))
        and isinstance(t.get("exit_timestamp"), (int, float))
        and t["exit_timestamp"] > t["timestamp"]
    ]
    if not hours:
        return 0.0, 0.0
    return round(sum(hours) / len(hours), 4), round(max(hours), 4)


def annualized_return_pct(total_return_pct: float, data_start_ns: int, data_end_ns: int) -> float:
    """真年化收益率（%，复利）：(1 + r)^(365 / 天数) − 1。

    天数 ≤ 0 或 (1 + r) ≤ 0（本金亏光）时不可年化 → 回退成原始总收益率。
    """
    days = (float(data_end_ns) - float(data_start_ns)) / 1e9 / 86400
    growth = 1.0 + float(total_return_pct) / 100.0
    if days <= 0 or growth <= 0:
        return round(float(total_return_pct), 4)
    return round((growth ** (365.0 / days) - 1.0) * 100.0, 4)
