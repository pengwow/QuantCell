"""回测稳健性指标 —— Deflated Sharpe Ratio（P1-04）与 PBO / Block Bootstrap
/ 成本压力 / 评级（P1-05）。

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

import itertools
import math
from bisect import bisect_left
from datetime import UTC, datetime, timezone

import numpy as np
import pandas as pd

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


# ==================== P1-05：PBO / Block Bootstrap / 成本压力 / 评级 ====================


def _ts_to_ms(ts: float) -> int:
    """时间戳（自动识别 秒/毫秒/微秒/纳秒 量级，阈值与 _year_of 一致）→ 毫秒。"""
    v = float(ts)
    if v > 1e17:
        return int(v // 1e6)
    if v > 1e14:
        return int(v // 1e3)
    if v > 1e11:
        return int(v)
    return int(v * 1e3)


def curve_returns(equity_curve: list[dict]) -> tuple[list[int], list[float], list[float]]:
    """权益曲线 → (毫秒时间戳, 逐 bar log 收益, 对应权益)，三个列表等长。

    收益归属于相邻两点中**后一点**（r = log(e[i]/e[i-1])），权益同为后一点值，
    时间戳即后一点时间。非 dict 点 / 非数值或非正权益点直接跳过。
    """
    pts: list[tuple[int, float]] = []
    for point in equity_curve or []:
        if not isinstance(point, dict):
            continue
        ts, eq = point.get("timestamp"), point.get("equity")
        if not (isinstance(ts, (int, float)) and isinstance(eq, (int, float))):
            continue
        if not (math.isfinite(float(eq)) and float(eq) > 0):
            continue
        pts.append((_ts_to_ms(float(ts)), float(eq)))

    ts_out: list[int] = []
    returns: list[float] = []
    eq_out: list[float] = []
    for i in range(1, len(pts)):
        ts_out.append(pts[i][0])
        returns.append(math.log(pts[i][1] / pts[i - 1][1]))
        eq_out.append(pts[i][1])
    return ts_out, returns, eq_out


def log_returns(equity_curve: list[dict]) -> list[float]:
    """权益曲线 → 逐 bar log 收益（不年化），供 bootstrap / 成本压力使用。"""
    return curve_returns(equity_curve)[1]


def _sharpe_unannualized(returns: list[float]) -> float | None:
    """样本 std 口径 sharpe（不年化）；不足 2 个收益或零方差 → None。"""
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    return mean / std if std > 0 else None


def block_bootstrap_sharpe(
    returns, n_paths: int = 1000, block: int | None = None, seed: int | None = None
) -> dict | None:
    """Moving Block Bootstrap 的 sharpe 置信区间（P1-05）。

    块长默认 max(5, int(len**(1/3)))；对收益序列整块有放回重采样 n_paths 次，
    每次 path 拼到与原序列等长后算 sharpe，得到经验分布。返回
    {"point", "p05", "p50", "p95", "n_paths", "block"}；收益 < 8 个或零方差 →
    None（样本太少 bootstrap 无意义，不造伪值）。seed 供测试/复现固定随机数。
    """
    r = np.asarray([float(x) for x in (returns or [])], dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 8:
        return None
    std = float(r.std(ddof=1))
    # ponytail: 全等元素序列的 np.std 因 mean 舍入可能返回 ~1e-18 非零，极差才能精确判零
    if not float(r.max() - r.min()) > 0 or not std > 0:
        return None
    point = float(r.mean() / std)

    blk = int(block) if block else max(5, int(n ** (1 / 3)))
    blk = max(1, min(blk, n))
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / blk)
    starts = rng.integers(0, n - blk + 1, size=(n_paths, n_blocks))
    idx = (starts[:, :, None] + np.arange(blk)).reshape(n_paths, -1)[:, :n]
    samples = r[idx]
    # 零方差 path（极端情况下全部重采样命中同一处）置 NaN，分位数计算时剔除；
    # 同上，mean 舍入会让 np.std 给出 ~1e-18 假非零，极差精确判零
    ok = np.ptp(samples, axis=1) > 0
    path_sharpe = np.where(ok, samples.mean(axis=1) / np.where(ok, samples.std(axis=1, ddof=1), 1.0), np.nan)
    q05, q50, q95 = np.nanpercentile(path_sharpe, [5, 50, 95])
    return {"point": point, "p05": float(q05), "p50": float(q50), "p95": float(q95), "n_paths": n_paths, "block": blk}


def _relative_rank(values: np.ndarray, idx: int) -> float:
    """values 中第 idx 元素的相对排位：平均秩（ties 取均值）归一到 0..1。"""
    x = values[idx]
    less = int(np.count_nonzero(values < x))
    equal = int(np.count_nonzero(values == x))
    mean_rank = less + 0.5 * (equal + 1)  # 并列组的平均秩：less+1 .. less+equal
    return (mean_rank - 1) / (len(values) - 1)  # len ≥ 2 由调用方保证


def pbo(returns_by_strategy: pd.DataFrame, n_splits: int = 16) -> float | None:
    """CSCV 回测过拟合概率 PBO（P1-05，Bailey et al. 2017）。

    输入 T×N 收益矩阵（列为"策略"；组合回测取各品种权益曲线的逐 bar log 收益，
    按时间戳对齐）。把时间轴切成 S=n_splits 个子块，枚举 C(S, S/2) 种 IS/OOS
    分割：IS 均值选出最优策略，看它在 OOS 的相对排位 ω，PBO = P(ω ≤ 0.5)，
    即"样本内赢家在样本外掉到中位以下"的频率，越低越可信。

    退化输入 → None（不造伪值）：
    - 策略列 < 2（单品种回测没有比较对象）
    - 有效行数 < n_splits（每块至少要有一个样本）
    - 列去重后 < 2（如共享资金池下各品种拿到同一账户曲线，列间无差异）
    """
    assert n_splits >= 8 and n_splits % 2 == 0, "n_splits 必须是 ≥8 的偶数（CSCV 对称性要求）"
    if returns_by_strategy is None or getattr(returns_by_strategy, "empty", True):
        return None
    matrix = np.asarray(returns_by_strategy.dropna(), dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] < 2 or matrix.shape[0] < n_splits:
        return None
    if np.unique(matrix, axis=1).shape[1] < 2:
        return None

    blocks = np.array_split(matrix, n_splits, axis=0)
    block_sums = np.vstack([b.sum(axis=0) for b in blocks])
    row_counts = np.asarray([b.shape[0] for b in blocks], dtype=float)
    split = n_splits // 2

    # 用逐块的列和 + 行数还原任意 IS/OOS 组合的均值，避免每个组合重复拼接大矩阵
    pbo_hits = 0
    combos = 0
    for is_idx in itertools.combinations(range(n_splits), split):
        is_set = set(is_idx)
        oos_idx = [i for i in range(n_splits) if i not in is_set]
        is_mean = block_sums[list(is_idx)].sum(axis=0) / row_counts[list(is_idx)].sum()
        oos_mean = block_sums[oos_idx].sum(axis=0) / row_counts[oos_idx].sum()
        best = int(np.argmax(is_mean))  # ties 取首列：并列频率在组合枚举下天然对称
        if _relative_rank(oos_mean, best) <= 0.5:
            pbo_hits += 1
        combos += 1
    return pbo_hits / combos


def cost_stress(equity_curve: list[dict], trades: list[dict], bps_grid=(1, 3, 5, 10)) -> list[dict] | None:
    """成本压力测试（P1-05）：在现有成交与权益曲线上叠加额外费率重算 sharpe。

    详设伪签名为 cost_stress(results, bps_grid)，实现取 results 的两个子字段
    保持纯函数（与 derived_metrics 同风格）。口径：
    - 每笔交易的双边额外成本 = 2 × bps/1e4 × entry_price×size（契约 trade 记录
      不含 exit_price，平仓名义额以 entry 近似）；成本挂到平仓时间所在的收益点
      （bisect_left 定位），从该点 log 收益一次性扣减 fee/equity —— 近似费用在
      成交时点真实支付。
    - sharpe 与 DSR 试验口径一致（逐 bar log 收益、样本 std、不年化）；
      bps=0 时即该口径的基准 sharpe。
    - 曲线有效收益点 < 3 → None（数据不足，样本 std 无意义）。
    """
    ts_ms, returns, eq = curve_returns(equity_curve)
    if len(returns) < 3:
        return None

    # 每笔下一次成交的名义额按平仓时点挂到对应收益点（bisect_left = 首个 ts ≥ 平仓时间的点）
    notional_at_bar: dict[int, float] = {}
    for t in trades or []:
        if not isinstance(t, dict):
            continue
        price = t.get("entry_price")
        size = t.get("size")
        if not (isinstance(price, (int, float)) and isinstance(size, (int, float))):
            continue
        notional = float(price) * float(size)
        if not math.isfinite(notional) or notional <= 0:
            continue
        e_ts = t.get("exit_timestamp")
        if not isinstance(e_ts, (int, float)):
            continue
        i = bisect_left(ts_ms, _ts_to_ms(float(e_ts)))
        i = min(i, len(ts_ms) - 1)  # 平仓时间超出曲线尾部的费用挂在最后一个点
        notional_at_bar[i] = notional_at_bar.get(i, 0.0) + notional

    out: list[dict] = []
    for bps in bps_grid:
        factor = 2.0 * bps / 1e4  # 双边（开仓+平仓各一次），bps 为单边费率
        adj = [returns[i] - notional_at_bar.get(i, 0.0) * factor / eq[i] for i in range(len(returns))]
        s = _sharpe_unannualized(adj)
        if s is None:
            continue
        out.append({"bps": bps, "sharpe": s})
    return out or None


def robustness_grade(metrics: dict) -> str:
    """稳健性综合评级（方案口径）：A=PBO<0.30 且 DSR>0；B=PBO<0.45 或 DSR>-0.5；其余 C。

    输入为 None（数据不足 / 内核缺位）时该条不参与判定，None 不算达标。
    """
    pbo_v = metrics.get("pbo")
    dsr_v = metrics.get("deflated_sharpe")
    if pbo_v is not None and pbo_v < 0.30 and dsr_v is not None and dsr_v > 0:
        return "A"
    if (pbo_v is not None and pbo_v < 0.45) or (dsr_v is not None and dsr_v > -0.5):
        return "B"
    return "C"
