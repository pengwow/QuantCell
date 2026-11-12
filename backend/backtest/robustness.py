"""回测稳健性指标 —— Deflated Sharpe Ratio（P1-04 接线）。

DSR 算法直调内核已实现（Bailey & López de Prado 2014）：Rust 侧
``axon_quant.walk_forward.py_deflated_sharpe``（``compute_deflated_sharpe``
直通，详见 axon-quant ``axon-walk-forward/src/evaluation.rs`` 与
``src/python/mod.rs``），不自研公式。实施设计要求"ImportError 时返回 None、
不降级为伪值"：内核缺位时相关指标输出 None，由前端展示为"—"。

试验（trial）口径：单次回测没有跨策略/跨参数的多 trial 上下文，本模块取
equity curve 按自然年分段的逐段 bar log 收益 sharpe（不年化，同一 timeframe
下段间可比）作为试验分布，语义为"剔除单年运气后的策略质量分"。

约定（与 derived_metrics.py 一致）：
- 纯函数、对空/退化输入返回空列表或 None，不抛异常
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timezone

try:
    # 内核 DSR 唯一公开入口。注意：实施设计写的 "axon_walk_forward.deflated_sharpe"
    # 在当前 wheel 中并不存在（该包仅导出私有 _deflated_sharpe），此名才是复核方案
    # 引用的 Rust 直通实现与内核单测基准所在。
    from axon_quant.walk_forward import py_deflated_sharpe as _dsr
except ImportError:  # pragma: no cover - 内核缺位属于环境异常，逻辑由测试 monkeypatch 覆盖
    _dsr = None


def deflated_sharpe(sharpes: list[float]) -> float | None:
    """试验 sharpe 序列 → Deflated Sharpe Ratio（0..1，越大越可信）。

    - 试验数 < 2：std 无法估计 → None（不造伪值）
    - 内核缺位（模块导入失败）→ None
    - 其余均值/个数/样本 std 直通内核 compute_deflated_sharpe
    """
    if _dsr is None or not sharpes or len(sharpes) < 2:
        return None
    n = len(sharpes)
    mean = sum(sharpes) / n
    variance = sum((s - mean) ** 2 for s in sharpes) / (n - 1)
    return float(_dsr(mean, n, math.sqrt(variance)))


def _year_of(ts: float) -> int:
    """时间戳（自动识别 秒/毫秒/微秒/纳秒 量级）→ UTC 年份。"""
    v = float(ts)
    if v > 1e17:
        v /= 1e9
    elif v > 1e14:
        v /= 1e6
    elif v > 1e11:
        v /= 1e3
    return datetime.fromtimestamp(v, tz=UTC).year


def yearly_sharpes(equity_curve: list[dict]) -> list[float]:
    """权益曲线 → 按自然年分段的逐段 bar log 收益 sharpe（不年化）。

    - 每"年段"内相邻净值点算 log 收益（每年首个点无前值，天然少一个收益，可忽略）
    - 段内收益不足 2 个或零方差（如纯现金持平段）时跳过该段
    """
    by_year: dict[int, list[float]] = {}
    for point in equity_curve or []:
        if not isinstance(point, dict):
            continue
        ts, eq = point.get("timestamp"), point.get("equity")
        if not (isinstance(ts, (int, float)) and isinstance(eq, (int, float))):
            continue
        if not (math.isfinite(float(eq)) and float(eq) > 0):
            continue
        by_year.setdefault(_year_of(float(ts)), []).append(float(eq))

    sharpes: list[float] = []
    for year in sorted(by_year):
        navs = by_year[year]
        returns = [math.log(navs[i] / navs[i - 1]) for i in range(1, len(navs)) if navs[i - 1] > 0]
        if len(returns) < 2:
            continue
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance)
        if std <= 0:
            continue
        sharpes.append(mean / std)
    return sharpes
