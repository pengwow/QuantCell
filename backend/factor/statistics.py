"""因子多重检验统计 —— BH / BY 假发现率（FDR）校正（P1-06）。

批量筛选因子时逐因子独立做显著性判断，伪显著数量随因子个数线性放大
（α=0.05 下 100 个因子期望混入约 5 个）。本模块在跨因子维度做
Benjamini-Hochberg（独立 / 正向依赖假设）与 Benjamini-Yekutieli
（任意依赖假设）两步法 FDR 校正。

- p 值来源：各因子 IC 序列对 H0（IC 均值 = 0）的双侧 t 检验（t_pvalue）。
- BH/BY 为纯 numpy 自实现（排序 step-up adjusted p-value），不依赖
  statsmodels；单测用 statsmodels.stats.multitest.multipletests 逐值
  对拍（<1e-12 门禁，见 tests/unit/factor/test_fdr.py）。
- 契约（与 backtest/robustness.py 一致）：纯函数；退化输入（空 / n<2 /
  零方差 / 无有效 p 值）返回 None 或 (None, None)，不造伪值。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats as _scipy_stats

FDR_METHODS = ("none", "bh", "by")

_ALPHA_DEFAULT = 0.05


def t_pvalue(ic_values: Iterable[float] | pd.Series) -> float | None:
    """IC 序列对 H0（均值 = 0）的双侧 t 检验 p 值。

    样本 std 口径（ddof=1），与 FactorService._ic_stats 的 t_stat 同源。
    有效样本 < 2 或零方差 → None（检验无意义，不造伪值）。
    """
    vals: list[float] = []
    for v in ic_values:
        if v is None:
            continue
        f = float(v)
        if math.isfinite(f):
            vals.append(f)
    x = np.asarray(vals, dtype=float)
    n = x.size
    if n < 2:
        return None
    std = float(x.std(ddof=1))
    if not std > 0:
        return None
    t_abs = abs(float(x.mean()) / (std / math.sqrt(n)))
    return float(2.0 * _scipy_stats.t.sf(t_abs, df=n - 1))


def _fdr_core(
    pvalues: Sequence[float | None], alpha: float, scale: float
) -> tuple[list[float | None], list[bool | None]]:
    """排序域 step-up adjusted p-value 的共用骨架。

    adj_(i) = clip( min_{j≥i} ( m·scale / j )·p_(j) , 0, 1 )，scale=1 即 BH，
    scale=c(m)=Σ1/i 即 BY（常数与 min 可交换，两种方法共用同一实现）。
    None / 非有限 p 直通为 (None, None)，有效个数 m 不含它们
    （与 statsmodels.multipletests 的 isfinite 过滤口径一致）。
    """
    p_list = list(pvalues)
    valid = [i for i, p in enumerate(p_list) if isinstance(p, (int, float)) and math.isfinite(float(p))]
    q_out: list[float | None] = [None] * len(p_list)
    sig_out: list[bool | None] = [None] * len(p_list)
    if not valid:
        return q_out, sig_out

    p_valid = np.asarray([float(p_list[i]) for i in valid], dtype=float)
    order = np.argsort(p_valid, kind="stable")
    m = p_valid.size
    raw = p_valid[order] * m * scale / np.arange(1, m + 1)
    # 从右往左累积最小值即 min_{j≥i}（step-up adjusted p-value），整体 clip 到 [0,1]
    adj_sorted = np.clip(np.minimum.accumulate(raw[::-1])[::-1], 0.0, 1.0)
    adj = np.empty(m)
    adj[order] = adj_sorted

    for pos, i in enumerate(valid):
        q_out[i] = float(adj[pos])
        sig_out[i] = bool(adj[pos] <= alpha)
    return q_out, sig_out


def benjamini_hochberg(
    pvalues: Sequence[float | None], alpha: float = _ALPHA_DEFAULT
) -> tuple[list[float | None], list[bool | None]]:
    """Benjamini-Hochberg FDR 校正（独立 / 正向依赖假设）。

    返回 (qvalues, rejected)：q 为校正后 p 值，rejected 为 q ≤ alpha。
    性质：m=1 时 q = p（单因子退化为普通检验）。
    """
    return _fdr_core(pvalues, alpha, scale=1.0)


def benjamini_yekutieli(
    pvalues: Sequence[float | None], alpha: float = _ALPHA_DEFAULT
) -> tuple[list[float | None], list[bool | None]]:
    """Benjamini-Yekutieli FDR 校正（任意依赖假设）。

    q = BH 的 adjusted × c(m)，c(m) = Σ_{i=1..m} 1/i（调和级数），clip 到 1。
    代价是比 BH 更保守；因子间相关性不可信时使用。
    """
    p_list = [p for p in pvalues if isinstance(p, (int, float)) and math.isfinite(float(p))]
    m = len(p_list)
    scale = sum(1.0 / i for i in range(1, m + 1)) if m else 1.0
    return _fdr_core(pvalues, alpha, scale=scale)


def annotate_fdr(
    rows: list[dict],
    ic_by_factor: pd.DataFrame | None,
    *,
    fdr_method: str | None = None,
    alpha: float = _ALPHA_DEFAULT,
) -> None:
    """在 compare 因子行上就地补 p_bh / p_by / significant_bh 三键。

    - p 值逐因子取各自 IC 序列的 t 检验（t_pvalue），BH/BY 在整批因子上
      联合校正一次（多重检验的正确口径，而非逐因子独立）；
    - fdr_method：none → 三键全部 None（不做任何校正主张）；bh / by →
      significant_bh 列名固定、判定口径随 method（bh 用 q_bh，by 用 q_by），
      由调用方解析（入参 > 全局配置 factor.fdr.method > 默认 bh）；
    - 因子在 ic_by_factor 中无 IC 序列（如全 None）→ 三键 None。
    """
    if fdr_method not in FDR_METHODS:
        fdr_method = "bh"
    if fdr_method == "none":
        for row in rows:
            row["p_bh"] = None
            row["p_by"] = None
            row["significant_bh"] = None
        return

    frame = ic_by_factor if ic_by_factor is not None else pd.DataFrame()
    names = [row.get("factor_name") for row in rows]
    pvals = [t_pvalue(frame[name]) if name in frame.columns else None for name in names]
    q_bh, sig_bh = benjamini_hochberg(pvals, alpha)
    q_by, sig_by = benjamini_yekutieli(pvals, alpha)

    for row, p_bh, p_by, s_bh, s_by in zip(rows, q_bh, q_by, sig_bh, sig_by, strict=True):
        row["p_bh"] = p_bh
        row["p_by"] = p_by
        row["significant_bh"] = s_bh if fdr_method == "bh" else s_by
