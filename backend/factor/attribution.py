"""因子绩效归因 — 因子值与未来收益的统计关系。

输入：因子特征帧（DatetimeIndex 行 = K 线，列 = 因子名）+ 收盘价序列；
输出：每个因子的 stats / IC / Rank IC / ICIR / 分组收益 / 多空收益。

纯函数，无副作用，可独立测试。归因失败时返回空 dict 或 null 值，不阻断回测主流程。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_factor_attribution(
    factor_df: pd.DataFrame,
    closes: pd.Series,
    n_groups: int = 5,
    forward_period: int = 1,
) -> dict[str, dict[str, Any]]:
    """逐因子计算归因指标。

    Args:
        factor_df: 因子特征帧，索引与 closes 对齐（DatetimeIndex），列为因子名。
        closes: 与 factor_df 同源索引的收盘价序列。
        n_groups: 分组数（默认 5）。
        forward_period: 前瞻收益期数（bar 数，默认 1）。

    Returns:
        {factor_name: {stats, ic, rank_ic, icir, group_returns, long_short_return}}；
        因子列全 NaN 或样本不足时该因子条目值为 {}。
    """
    if factor_df is None or factor_df.empty or closes is None or len(closes) < 2:
        return {}

    # 对齐时区：特征帧可能是 naive datetime，closes 可能是 tz-aware，统一到 UTC
    f_idx = pd.DatetimeIndex(factor_df.index)
    c_idx = pd.DatetimeIndex(closes.index)
    if f_idx.tz is None:
        f_idx = f_idx.tz_localize("UTC")
    else:
        f_idx = f_idx.tz_convert("UTC")
    if c_idx.tz is None:
        c_idx = c_idx.tz_localize("UTC")
    else:
        c_idx = c_idx.tz_convert("UTC")

    common_idx = f_idx.intersection(c_idx)
    if len(common_idx) < 2:
        return {}

    # factor_df 索引可能是 naive，需转成与 common_idx 一致的 tz-aware 才能 .loc
    factor_df = factor_df.copy()
    factor_df.index = f_idx
    aligned_factors = factor_df.loc[common_idx]
    aligned_closes = closes.loc[common_idx]

    # 前瞻收益：close[t+N] / close[t] - 1
    fwd_ret = aligned_closes.pct_change(periods=forward_period).shift(-forward_period)

    attribution: dict[str, dict[str, Any]] = {}
    for col in aligned_factors.columns:
        factor_vals = aligned_factors[col]
        valid = factor_vals.notna() & fwd_ret.notna()
        if valid.sum() < 10:  # 样本太少，统计无意义
            attribution[col] = {}
            continue

        fv = factor_vals[valid]
        fr = fwd_ret[valid]

        stats = _compute_stats(fv)
        ic = _safe_corr(fv, fr, method="pearson")
        rank_ic = _safe_corr(fv, fr, method="spearman")
        icir = _compute_icir(factor_vals, fwd_ret, valid)
        group_returns = _compute_group_returns(fv, fr, n_groups)
        long_short = _compute_long_short(group_returns)

        attribution[col] = {
            "stats": stats,
            "ic": ic,
            "rank_ic": rank_ic,
            "icir": icir,
            "group_returns": group_returns,
            "long_short_return": long_short,
        }

    return attribution


def _compute_stats(values: pd.Series) -> dict[str, float]:
    """基础统计量（跳过 NaN）。"""
    s = values.dropna()
    if s.empty:
        return {}
    return {
        "mean": float(s.mean()),
        "std": float(s.std()),
        "min": float(s.min()),
        "max": float(s.max()),
        "median": float(s.median()),
        "q25": float(s.quantile(0.25)),
        "q75": float(s.quantile(0.75)),
    }


def _safe_corr(x: pd.Series, y: pd.Series, method: str) -> float | None:
    """安全计算相关系数，失败时返回 None。"""
    try:
        if len(x) < 2 or len(y) < 2:
            return None
        val = x.corr(y, method=method)
        if pd.isna(val):
            return None
        return round(float(val), 6)
    except Exception:
        return None


def _compute_icir(factor_vals: pd.Series, fwd_ret: pd.Series, valid: pd.Series) -> float | None:
    """ICIR = 滚动 IC 均值 / 滚动 IC 标准差，衡量因子预测能力的稳定性。

    滚动窗口 = min(60, 样本数/4)；窗口内 IC 不足 2 个则跳过。
    """
    n = valid.sum()
    if n < 20:
        return None
    window = min(60, max(10, n // 4))

    fv = factor_vals[valid]
    fr = fwd_ret[valid]
    ics: list[float] = []
    for i in range(window, len(fv) + 1):
        seg_fv = fv.iloc[i - window : i]
        seg_fr = fr.iloc[i - window : i]
        ic = seg_fv.corr(seg_fr, method="pearson")
        if not pd.isna(ic):
            ics.append(float(ic))

    if len(ics) < 2:
        return None
    ic_arr = np.array(ics)
    std = float(ic_arr.std())
    if std == 0:
        return None
    return round(float(ic_arr.mean() / std), 6)


def _compute_group_returns(factor_vals: pd.Series, fwd_ret: pd.Series, n_groups: int) -> dict[str, float]:
    """按因子值分 n_groups 组（qcut），每组计算平均前瞻收益。"""
    try:
        groups = pd.qcut(factor_vals, q=n_groups, labels=False, duplicates="drop")
        result: dict[str, float] = {}
        for g in sorted(groups.dropna().unique()):
            mask = groups == g
            mean_ret = fwd_ret[mask].mean()
            if pd.notna(mean_ret):
                result[f"g{int(g) + 1}"] = round(float(mean_ret), 6)
        return result
    except Exception:
        return {}


def _compute_long_short(group_returns: dict[str, float]) -> float | None:
    """多空收益 = top 组平均收益 - bottom 组平均收益。"""
    if len(group_returns) < 2:
        return None
    sorted_keys = sorted(group_returns.keys(), key=lambda k: int(k[1:]))
    bottom = group_returns[sorted_keys[0]]
    top = group_returns[sorted_keys[-1]]
    return round(top - bottom, 6)
