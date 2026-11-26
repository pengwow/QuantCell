"""风控建议层 v1（设计 P4-2）：只读评估端口，仅输出告警与建议额度。

红线（改动前先读）
-----------------
本模块是**纯只读评估**：不 import、不调用 ``worker.risk_config`` 的任何写路径
（``push_risk_control`` / ``apply_risk_config`` / ``resolve_risk_settings``），
不写 ``params.risk``、不写 ``worker_risk_control``、不热更引擎 RiskConfig。
硬规则链路（``worker/risk_config.py``）保持不变——建议额度只是 advisory dict 里
的一个数字，是否落到硬规则由人确认后走既有入口。
``tests/unit/agent/test_risk_advisory.py`` 用 AST 静态断言守护这条红线。

指标口径（参数法近似，阈值宽松起步）
-----------------------------------
- EWMA 日波动率：RiskMetrics 口径，均值按 0 处理，λ 固定
- 当前回撤：由日收益序列复利出权益曲线，取峰值到当前的最大跌幅
- VaR95：参数法（正态假设），``-(mean - 1.645 * std)``，只取正值为潜在日亏损比例
- 名义集中度：单品种绝对名义额 / 该 worker 全部持仓名义额合计（与 daily_review
  的 ``_position_anomalies`` 同口径，但这里额外给「建议单品种名义上限」）

ponytail: 样本是 ``get_trade_history_chart`` 的按日补零序列（空仓日收益 0），
样本不足/权益未知时不硬算，直接跳过该类 advisory；升级路径是换逐笔权益快照 +
t 分布/历史模拟 VaR。阈值是常量而不是配置项——建议层先证明自己有用，再谈可调。
"""

from __future__ import annotations

import json
import math
import statistics
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 近窗收益序列长度（天）
WINDOW_DAYS = 30
# RiskMetrics EWMA 衰减因子
EWMA_LAMBDA = 0.94
# 95% 单尾正态分位
VAR95_Z = 1.645

# 日波动率阈值（0.03 ≈ 年化 48%，宽松起步）
DAILY_VOL_WARN = 0.03
DAILY_VOL_CRIT = 0.06
# 回撤阈值
DRAWDOWN_WARN = 0.10
DRAWDOWN_CRIT = 0.20
# VaR95 阈值（单日潜在亏损 / 权益）
VAR95_WARN = 0.04
VAR95_CRIT = 0.08
# 单品种名义集中度阈值（%）
CONCENTRATION_WARN = 60.0
CONCENTRATION_CRIT = 85.0
# info 档：达到 warn 阈值的这一比例即提示「接近阈值」
INFO_RATIO = 0.8
# 建议额度基线：名义敞口 / 权益（健康态视为 1.0 倍，超阈值按比例压缩）
BASE_GROSS_EXPOSURE_RATIO = 1.0

SEVERITY_ORDER = {"info": 0, "warn": 1, "crit": 2}


# ---------- 指标（纯函数） ----------


def _finite(values: Any) -> list[float]:
    """过滤 None / 非数字 / NaN / inf，保留有限浮点。"""
    out: list[float] = []
    for v in values or ():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def ewma_volatility(returns: Any, lam: float = EWMA_LAMBDA) -> float:
    """EWMA 日波动率（单参数，均值按 0）。样本不足 2 个返回 0。"""
    rs = _finite(returns)
    if len(rs) < 2:
        return 0.0
    var = rs[0] ** 2
    for r in rs[1:]:
        var = lam * var + (1.0 - lam) * r * r
    return math.sqrt(max(var, 0.0))


def max_drawdown(returns: Any) -> float:
    """由日收益复利出权益曲线后的最大回撤（正数比例）。"""
    rs = _finite(returns)
    equity = peak = 1.0
    worst = 0.0
    for r in rs:
        equity *= 1.0 + r
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return worst


def parametric_var95(returns: Any) -> float:
    """参数法 VaR95（正数 = 单日潜在亏损占权益比例）。"""
    rs = _finite(returns)
    if len(rs) < 2:
        return 0.0
    mean = statistics.fmean(rs)
    std = statistics.stdev(rs)
    return max(0.0, -(mean - VAR95_Z * std))


def nominal_concentration(positions: Any) -> tuple[float, str | None, float]:
    """返回 (最大单品种名义占比 %, 该品种, 持仓总名义额)。"""
    book = 0.0
    worst_symbol: str | None = None
    worst_value = 0.0
    for p in positions or ():
        quantity = abs(float(p.get("quantity") or 0.0))
        price = float(p.get("current_price") or p.get("entry_price") or 0.0)
        value = abs(quantity * price)
        book += value
        if value > worst_value:
            worst_symbol = p.get("symbol")
            worst_value = value
    if book <= 0:
        return 0.0, worst_symbol, 0.0
    return worst_value / book * 100.0, worst_symbol, book


# ---------- 评级与建议额度 ----------


def _severity(value: float, warn: float, crit: float) -> str | None:
    """三档评定：crit ≥ crit 阈值，warn ≥ warn 阈值，info ≥ 80% warn，否则 None。"""
    if value >= crit:
        return "crit"
    if value >= warn:
        return "warn"
    if warn > 0 and value >= warn * INFO_RATIO:
        return "info"
    return None


def _cap_suggestion(equity: float, value: float, threshold: float) -> tuple[float | None, float | None]:
    """按「超出阈值的倍数」压缩名义敞口比例，返回 (建议名义上限, 建议比例)。"""
    if equity <= 0 or value <= 0:
        return None, None
    ratio = BASE_GROSS_EXPOSURE_RATIO * min(1.0, threshold / value)
    ratio = round(max(ratio, 0.0), 4)
    return round(equity * ratio, 2), ratio


def _advisory(
    *,
    worker_id: int,
    worker_name: str,
    metric: str,
    severity: str,
    value: float,
    threshold: float,
    reason: str,
    suggested_notional_cap: float | None = None,
    suggested_ratio: float | None = None,
) -> dict[str, Any]:
    return {
        "worker_id": worker_id,
        "worker_name": worker_name,
        "metric": metric,
        "severity": severity,
        "value": round(float(value), 6),
        "threshold": round(float(threshold), 6),
        "reason": reason,
        "suggested_notional_cap": suggested_notional_cap,
        "suggested_ratio": suggested_ratio,
    }


def assess_worker(
    *,
    worker_id: int,
    worker_name: str,
    returns: Any,
    positions: Any = (),
    equity: float = 0.0,
    window_days: int = WINDOW_DAYS,
) -> dict[str, Any]:
    """单 worker 评估：指标 + advisory 列表（健康态 advisories 为空）。"""
    rs = _finite(returns)
    equity = float(equity or 0.0)
    vol = ewma_volatility(rs)
    drawdown = max_drawdown(rs)
    var95 = parametric_var95(rs)
    concentration_pct, concentration_symbol, book_value = nominal_concentration(positions)

    metrics = {
        "window_days": window_days,
        "samples": len(rs),
        "equity": round(equity, 2),
        "ewma_vol": round(vol, 6),
        "max_drawdown": round(drawdown, 6),
        "var95": round(var95, 6),
        "concentration_pct": round(concentration_pct, 2),
        "concentration_symbol": concentration_symbol,
        "book_value": round(book_value, 2),
    }

    advisories: list[dict[str, Any]] = []

    severity = _severity(vol, DAILY_VOL_WARN, DAILY_VOL_CRIT)
    if severity:
        cap, ratio = _cap_suggestion(equity, vol, DAILY_VOL_WARN)
        advisories.append(
            _advisory(
                worker_id=worker_id,
                worker_name=worker_name,
                metric="volatility",
                severity=severity,
                value=vol,
                threshold=DAILY_VOL_WARN,
                reason=(
                    f"{worker_name} 近 {window_days} 日 EWMA 日波动率 {vol:.2%} 达 {severity} 档"
                    f"（阈值 {DAILY_VOL_WARN:.2%}）" + (f"，建议名义敞口上限降至 {cap:.2f}" if cap is not None else "")
                ),
                suggested_notional_cap=cap,
                suggested_ratio=ratio,
            )
        )

    severity = _severity(drawdown, DRAWDOWN_WARN, DRAWDOWN_CRIT)
    if severity:
        cap, ratio = _cap_suggestion(equity, drawdown, DRAWDOWN_WARN)
        advisories.append(
            _advisory(
                worker_id=worker_id,
                worker_name=worker_name,
                metric="drawdown",
                severity=severity,
                value=drawdown,
                threshold=DRAWDOWN_WARN,
                reason=(
                    f"{worker_name} 当前回撤 {drawdown:.2%} 达 {severity} 档（阈值 {DRAWDOWN_WARN:.2%}）"
                    + (f"，建议名义敞口上限降至 {cap:.2f}" if cap is not None else "")
                ),
                suggested_notional_cap=cap,
                suggested_ratio=ratio,
            )
        )

    severity = _severity(var95, VAR95_WARN, VAR95_CRIT)
    if severity:
        cap, ratio = _cap_suggestion(equity, var95, VAR95_WARN)
        advisories.append(
            _advisory(
                worker_id=worker_id,
                worker_name=worker_name,
                metric="var95",
                severity=severity,
                value=var95,
                threshold=VAR95_WARN,
                reason=(
                    f"{worker_name} 参数法 VaR95 {var95:.2%} 达 {severity} 档（阈值 {VAR95_WARN:.2%}），"
                    "即单日潜在亏损接近风控容忍度" + (f"，建议名义敞口上限降至 {cap:.2f}" if cap is not None else "")
                ),
                suggested_notional_cap=cap,
                suggested_ratio=ratio,
            )
        )

    severity = _severity(concentration_pct, CONCENTRATION_WARN, CONCENTRATION_CRIT)
    if severity:
        cap = round(book_value * CONCENTRATION_WARN / 100.0, 2) if book_value > 0 else None
        ratio = round(cap / equity, 4) if cap is not None and equity > 0 else None
        advisories.append(
            _advisory(
                worker_id=worker_id,
                worker_name=worker_name,
                metric="concentration",
                severity=severity,
                value=concentration_pct,
                threshold=CONCENTRATION_WARN,
                reason=(
                    f"{worker_name} {concentration_symbol or '单品种'} 名义集中度 {concentration_pct:.1f}% "
                    f"达 {severity} 档（阈值 {CONCENTRATION_WARN:.0f}%）"
                    + (f"，建议单品种名义上限 {cap:.2f}" if cap is not None else "")
                ),
                suggested_notional_cap=cap,
                suggested_ratio=ratio,
            )
        )

    return {
        "worker_id": worker_id,
        "worker_name": worker_name,
        "metrics": metrics,
        "advisories": advisories,
    }


# ---------- 数据装配（只读查询） ----------


def _worker_equity(db: Any, worker_id: int) -> float:
    """worker 权益基数：``Worker.config.initial_capital``（与 stats_service 同源）。

    缺失/脏数据返回 0 → 波动率类 advisory 跳过，集中度仍可评估。
    """
    from worker.models import Worker

    row = db.query(Worker.config).filter(Worker.id == worker_id).first()
    if row is None or not row[0]:
        return 0.0
    try:
        config = json.loads(row[0])
        return float(config.get("initial_capital", 0.0)) if isinstance(config, dict) else 0.0
    except (TypeError, ValueError):
        return 0.0


def collect_risk_advisories(workers: Any, *, window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    """对活跃 worker 列表做只读评估，返回可并入复盘 report 的 section。

    ``workers`` 为 daily_review 已聚合的 worker dict（含 positions），本函数只补
    近窗收益序列与权益基数，不重复查 worker 列表、不触碰任何写路径。
    """
    from utils.db_session import get_db_session
    from worker import crud

    if not workers:
        return {"window_days": window_days, "workers": [], "advisories": [], "count": 0, "max_severity": None}

    assessments: list[dict[str, Any]] = []
    with get_db_session() as db:
        for w in workers or ():
            worker_id = int(w["worker_id"])
            worker_name = str(w.get("name") or "")
            equity = 0.0
            returns: list[float] = []
            try:
                equity = _worker_equity(db, worker_id)
                if equity > 0:
                    chart = crud.get_trade_history_chart(db, worker_id, days=window_days)
                    returns = [float(p or 0.0) / equity for p in chart.get("daily_pnl") or ()]
            except Exception as e:  # 单个 worker 查询失败不该中断整份复盘
                logger.warning(f"[risk_advisory] worker 收益序列读取失败 worker_id={worker_id}: {e}")
                equity, returns = 0.0, []
            assessments.append(
                assess_worker(
                    worker_id=worker_id,
                    worker_name=worker_name,
                    returns=returns,
                    positions=w.get("positions") or (),
                    equity=equity,
                    window_days=window_days,
                )
            )

    advisories = [a for item in assessments for a in item["advisories"]]
    max_severity = None
    if advisories:
        max_severity = max((a["severity"] for a in advisories), key=lambda s: SEVERITY_ORDER.get(s, 0))
    return {
        "window_days": window_days,
        "workers": assessments,
        "advisories": advisories,
        "count": len(advisories),
        "max_severity": max_severity,
    }
