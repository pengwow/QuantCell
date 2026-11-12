"""P1-06 多重检验 FDR 测试：BH/BY 自实现 ↔ statsmodels 逐值对拍 + compare 挂接。"""

import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp
from statsmodels.stats.multitest import multipletests

from factor.service import FactorService
from factor.statistics import annotate_fdr, benjamini_hochberg, benjamini_yekutieli, t_pvalue

# ==================== BH 已知解等价性 ====================


def test_bh_rejection_count_matches_step_up_definition():
    """rejected 个数 = 满足 p_(k) ≤ k/m·α 的最大 k（BH 阶跃定义，实施设计验收项）。"""
    alpha = 0.05
    pvals = [
        0.001,
        0.008,
        0.039,
        0.041,
        0.042,
        0.06,
        0.074,
        0.205,
        0.212,
        0.216,
        0.222,
        0.251,
        0.269,
        0.275,
        0.34,
        0.341,
        0.384,
        0.569,
        0.594,
        0.696,
        0.762,
        0.94,
        0.942,
        0.975,
        0.986,
    ]
    m = len(pvals)
    s = sorted(pvals)
    k_max = 0
    for k in range(m, 0, -1):
        if s[k - 1] <= alpha * k / m:
            k_max = k
            break
    _, rejected = benjamini_hochberg(pvals, alpha)
    assert sum(r is True for r in rejected) == k_max
    # 且恰为排序后前 k_max 个 p 对应的位置
    order = np.argsort(pvals, kind="stable")
    for pos, idx in enumerate(order.tolist()):
        assert rejected[idx] is (pos < k_max)


# ==================== statsmodels 逐值对拍（<1e-12 门禁） ====================


def _assert_matches_statsmodels(pvals: list[float | None]):
    """逐值对拍：None 位断言直通 None；有效位在**有效子集**上调用 statsmodels。

    注意 statsmodels.multipletests 不做 nan 过滤（nan 计入 ntests 且 argsort
    排尾，会污染邻近结果），含缺失时官方正确用法即调用方先过滤——与我们
    实现的「m = 有效个数」口径一致。
    """
    valid_idx = [i for i, p in enumerate(pvals) if p is not None]
    valid = [pvals[i] for i in valid_idx]
    for method, impl in (("fdr_bh", benjamini_hochberg), ("fdr_by", benjamini_yekutieli)):
        q, _ = impl(pvals)
        _, corrected, _, _ = multipletests(valid, method=method)
        for pos, i in enumerate(valid_idx):
            assert abs(q[i] - corrected[pos]) < 1e-12, f"{method}: {q[i]} vs {corrected[pos]}"
        for i, p in enumerate(pvals):
            if p is None:
                assert q[i] is None


def test_bh_matches_statsmodels_random_and_edges():
    rng = np.random.default_rng(42)
    _assert_matches_statsmodels(list(rng.uniform(0, 1, 64)))
    _assert_matches_statsmodels(list(rng.uniform(0, 1, 7)))
    # 边界：单值（验收：q = p）、全 1、全 0
    _assert_matches_statsmodels([0.03])
    _assert_matches_statsmodels([1.0, 1.0, 1.0, 1.0])
    _assert_matches_statsmodels([0.0, 0.0, 0.0])
    # 含 None（缺失直通）
    _assert_matches_statsmodels([0.2, None, 0.01, 0.4, None, 0.9])
    # 含 p=0 与 p=1 端点
    _assert_matches_statsmodels([0.0, 0.5, 1.0])
    # 含并列值（ties）
    _assert_matches_statsmodels([0.04, 0.04, 0.04, 0.7, 0.7])


def test_by_matches_statsmodels_and_is_conservative_vs_bh():
    rng = np.random.default_rng(7)
    pvals = list(rng.uniform(0, 1, 33))
    q_by, _ = benjamini_yekutieli(pvals)
    q_bh, _ = benjamini_hochberg(pvals)
    # BY ≥ BH（调和级数系数 c(m) ≥ 1，任意依赖假设下更保守）
    assert all(b >= a for a, b in zip(q_bh, q_by, strict=True))
    _assert_matches_statsmodels(pvals)


# ==================== t 检验 p 值 ====================


def test_t_pvalue_matches_scipy_ttest_1samp():
    rng = np.random.default_rng(3)
    for n in (2, 5, 30, 500):
        x = rng.normal(0.3, 1.0, n)
        _, p_ref = ttest_1samp(x, 0.0)
        p = t_pvalue(x)
        assert p is not None and abs(p - p_ref) < 1e-12


def test_t_pvalue_rejects_degenerate_inputs():
    assert t_pvalue([0.1, np.nan, None]) is None  # 有效样本 < 2
    assert t_pvalue([0.5, 0.5, 0.5]) is None  # 零方差
    assert t_pvalue([]) is None


# ==================== annotate_fdr 与 compare 挂接 ====================


def test_annotate_fdr_methods():
    frame = pd.DataFrame(
        {
            "f1": [0.1, np.nan, 0.3, 0.2],
            "f2": [-0.1, 0.2, np.nan, -0.3],
        }
    )
    rows = [{"factor_name": "f1", "ic_mean": 0.2}, {"factor_name": "f2", "ic_mean": -0.1}]
    # none：三键全 None，不做校正主张
    annotate_fdr(rows, frame, fdr_method="none")
    assert all(r["p_bh"] is None and r["p_by"] is None and r["significant_bh"] is None for r in rows)
    # bh：列存在、值域合法、显著列与 q_bh 口径一致、BY ≥ BH
    annotate_fdr(rows, frame, fdr_method="bh")
    for r in rows:
        assert isinstance(r["p_bh"], float) and 0.0 <= r["p_bh"] <= 1.0
        assert isinstance(r["p_by"], float) and r["p_by"] >= r["p_bh"]
        assert r["significant_bh"] is (r["p_bh"] <= 0.05)
    # by 开关：significant 判定口径切到 q_by
    annotate_fdr(rows, frame, fdr_method="by")
    for r in rows:
        assert r["significant_bh"] is (r["p_by"] <= 0.05)


def test_annotate_fdr_missing_ic_series_yields_none():
    rows = [{"factor_name": "f1"}, {"factor_name": "ghost"}]
    frame = pd.DataFrame({"f1": [np.nan, np.nan]})
    annotate_fdr(rows, frame, fdr_method="bh")
    assert rows[0]["p_bh"] is None and rows[0]["significant_bh"] is None
    assert rows[1]["p_by"] is None


def test_compare_rows_carry_fdr_columns():
    """compare 真实链路：factors 行含 FDR 三键（默认 bh 经 get_value 读到）。"""
    from tests.unit.factor.test_compare import _KlineProvider

    res = FactorService().compare_factors(
        factor_names=["momentum_5d", "rsi_14d"],
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1h",
        candle_type="spot",
        start=None,
        end=None,
        provider=_KlineProvider(),
    )
    for row in res["factors"]:
        assert {"p_bh", "p_by", "significant_bh"} <= set(row)
        if row["p_bh"] is not None:
            assert row["p_by"] >= row["p_bh"]
            assert isinstance(row["significant_bh"], bool)


def test_compare_fdr_method_none_suppresses():
    from tests.unit.factor.test_compare import _KlineProvider

    res = FactorService().compare_factors(
        factor_names=["momentum_5d", "rsi_14d"],
        symbols=["BTCUSDT"],
        interval="1h",
        candle_type="spot",
        start=None,
        end=None,
        provider=_KlineProvider(),
        fdr_method="none",
    )
    assert all(r["p_bh"] is None and r["p_by"] is None and r["significant_bh"] is None for r in res["factors"])
