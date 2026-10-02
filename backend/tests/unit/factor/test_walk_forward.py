# 滚动 walk-forward 样本外复核（FactorService 层）：
# 边界切分 / 逐折沙箱执行 / 纯函数汇总 / 短数据容错 / 关闭兼容
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from factor.code_store import CodeFactorStore
from factor.engine import _timestamps_to_datetime
from factor.sandbox import FactorSandbox
from factor.service import FactorService

MOM_CODE = 'factor = df["close"].pct_change(5)'


def make_raw_map(n=240, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
    """与 test_llm_miner.Provider 同构的合成数据：注入截面趋势让动量有非零 IC。"""
    frames = {}
    for k, sym in enumerate(symbols):
        r = np.random.default_rng(10 + k)
        close = 100 + np.cumsum(r.normal(0, 1, n))
        ts = pd.date_range("2026-01-01", periods=n, freq="1h")
        close = close + np.arange(n) * (0.01 * (k + 1))
        frames[sym] = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": r.uniform(100, 1000, n),
                "quote_volume": close * 100,
                "timestamp": ts.astype("int64"),
            }
        )
    return frames


@pytest.fixture
def service(tmp_path):
    return FactorService(code_store=CodeFactorStore(tmp_path / "wf.json"), sandbox=FactorSandbox())


# ---------------------------------------------------------------------------
# 1) _wf_bounds：k 折边界单调、连续、不重叠、覆盖整个 OOS 区间
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("k", [2, 3, 4, 6])
def test_wf_bounds_partition_oos_span(k):
    raw_map = make_raw_map(n=240)
    bounds = FactorService._wf_bounds(raw_map, 0.3, k)

    assert len(bounds) == k
    pooled = pd.concat([_timestamps_to_datetime(df["timestamp"]) for df in raw_map.values()])
    oos_start = pooled.quantile(0.7)
    oos_end = pooled.max()

    assert bounds[0][0] == oos_start
    assert bounds[-1][1] == oos_end
    for i, (start, end) in enumerate(bounds):
        assert start < end
        # 左闭右开相邻折首尾相接：连续覆盖、无重叠
        if i > 0:
            assert start == bounds[i - 1][1]
    # 等长 3 品种：折 1 起点 == 全局 70% 分位（线性插值 t167 与 t168 间 0.3h，
    # 与 _split_raw_map 切点完全同源；按行序切 train 恰为 168 行）
    assert bounds[0][0] == pd.Timestamp("2026-01-07 23:18:00")
    for df in raw_map.values():
        dt = _timestamps_to_datetime(df["timestamp"])
        assert len(df[dt.to_numpy() < bounds[0][0].to_numpy()]) == 168


def test_wf_bounds_equal_linear_quantiles_on_balanced_panel():
    raw_map = make_raw_map(n=240)
    bounds = FactorService._wf_bounds(raw_map, 0.3, 3)
    # 等长等频时间网格上，内边界落在 OOS 的 1/3、2/3 分位（t191.67 / t215.33 附近）
    assert bounds[0][1] == bounds[1][0]
    assert bounds[1][1] == bounds[2][0]
    assert pd.Timestamp("2026-01-08 23:00") < bounds[0][1] < pd.Timestamp("2026-01-09 01:00")


# ---------------------------------------------------------------------------
# 2) 3 折复核：每折结构完整、bar_count>0、合成动量数据下 IC 非 None
# ---------------------------------------------------------------------------


def test_analyze_code_panel_walk_forward_three_folds(service):
    raw_map = make_raw_map(n=240)
    result = service.analyze_code_panel(
        MOM_CODE,
        raw_map,
        interval="1h",
        wf_folds=3,
        test_ratio=0.3,
        label="wf_candidate",
    )

    assert set(result) == {"train", "test", "wf", "train_factor"}
    assert result["test"] is None
    # train_factor：train_map 上的 MultiIndex(datetime,symbol) 因子面板（内部字段）
    assert isinstance(result["train_factor"], pd.Series)
    assert result["train_factor"].index.names == ["datetime", "symbol"]
    wf = result["wf"]
    folds = wf["folds"]
    assert len(folds) == 3
    for i, fold in enumerate(folds):
        assert fold["index"] == i
        assert pd.Timestamp(fold["start"]) < pd.Timestamp(fold["end"])
        assert fold["bar_count"] > 0
        assert fold["ic_mean"] is not None
        assert fold["positive_rate"] is not None
        assert 0 < fold["coverage"] <= 1
        assert set(fold) == {
            "index",
            "start",
            "end",
            "ic_mean",
            "ic_std",
            "positive_rate",
            "coverage",
            "bar_count",
        }
    # 等长切分下每折窗口 24 个时间点 × 3 品种，前瞻 dropna 后 23×3=69 行
    assert [f["bar_count"] for f in folds] == [69, 69, 69]

    assert wf["n_folds"] == 3
    assert wf["valid_folds"] == 3
    assert wf["ic_mean"] is not None
    assert wf["ic_ir"] is not None
    # 合成动量各折方向大体一致（具体值随数据，允许个别折噪声反向）
    assert wf["sign_consistency"] is not None
    assert wf["sign_consistency"] >= 2 / 3
    assert wf["bar_count"] == 207
    assert wf["oos_flag"] in {"ok", "weak", "sign_flip"}
    # fitness/排序口径不变：train analysis 仍是完整 _analyze_core 结果
    assert result["train"]["factor_name"] == "wf_candidate"
    assert "inspection" in result["train"]


# ---------------------------------------------------------------------------
# 3) 关闭兼容：wf_folds=0 / 1 时完全走旧路径，wf 恒为 None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf_folds", [0, 1])
def test_wf_disabled_keeps_legacy_shape(service, wf_folds):
    raw_map = make_raw_map(n=240)
    result = service.analyze_code_panel(
        MOM_CODE,
        raw_map,
        interval="1h",
        wf_folds=wf_folds,
        test_ratio=0.3,
        label="legacy",
    )
    assert "train" in result and "test" in result
    assert result["wf"] is None
    assert result["test"] is not None
    assert "inspection" in result["test"]
    # 单次切分路径同样透出 train 段因子面板
    assert isinstance(result["train_factor"], pd.Series)


# ---------------------------------------------------------------------------
# 4) 沙箱执行 1(train)+k 次，前缀行数单调不减（禁止全量结果切片）
# ---------------------------------------------------------------------------


def test_each_fold_runs_sandbox_on_growing_prefix(service, monkeypatch):
    raw_map = make_raw_map(n=240)
    original_run = service._sandbox.run
    segment_rows = []

    def spy(code, frames):
        segment_rows.append(len(next(iter(frames.values()))))
        return original_run(code, frames)

    monkeypatch.setattr(service._sandbox, "run", spy)

    service.analyze_code_panel(MOM_CODE, raw_map, interval="1h", wf_folds=3, test_ratio=0.3, label="spy")

    # train=168；折前缀分别截止 t191/t215/t239 → 192/216/240，严格递增
    assert segment_rows == [168, 192, 216, 240]
    assert all(b >= a for a, b in pairwise(segment_rows))
    assert len(segment_rows) == 1 + 3


# ---------------------------------------------------------------------------
# 5) _aggregate_wf 纯函数表驱动：加权 IC / 折间 std / 符号一致性 / 空折剔除 / flag
# ---------------------------------------------------------------------------


def _fold(index, ic_mean, *, bar_count=10, coverage=0.8, ic_std=None, positive_rate=None):
    return {
        "index": index,
        "start": "2026-01-01T00:00:00",
        "end": "2026-01-02T00:00:00",
        "ic_mean": ic_mean,
        "ic_std": ic_std,
        "positive_rate": positive_rate,
        "coverage": coverage,
        "bar_count": bar_count,
    }


def test_aggregate_wf_weights_ic_and_coverage_by_bar_count():
    folds = [_fold(0, 0.10, bar_count=10, coverage=0.5), _fold(1, 0.30, bar_count=30, coverage=0.9)]
    metrics, flag, note = FactorService._aggregate_wf(folds, 0.2)
    assert metrics["ic_mean"] == pytest.approx(0.25)
    assert metrics["coverage"] == pytest.approx(0.8)  # (0.5*10+0.9*30)/40
    assert metrics["bar_count"] == 40
    assert metrics["n_folds"] == 2
    assert metrics["valid_folds"] == 2
    assert metrics["sign_consistency"] == 1.0
    assert flag == "ok"
    assert note is None


def test_aggregate_wf_inter_fold_std_and_ir_ddof1():
    folds = [_fold(0, 0.1), _fold(1, 0.2), _fold(2, 0.3)]
    metrics, _, _ = FactorService._aggregate_wf(folds, 0.2)
    assert metrics["ic_std"] == pytest.approx(0.1)  # 折间样本标准差 ddof=1
    assert metrics["ic_ir"] == pytest.approx(2.0)
    assert metrics["sign_consistency"] == 1.0


def test_aggregate_wf_sign_consistency_is_majority_fraction():
    folds = [_fold(0, 0.1, bar_count=1), _fold(1, -0.05, bar_count=1), _fold(2, 0.2, bar_count=2)]
    metrics, _, _ = FactorService._aggregate_wf(folds, 0.1)
    # 加权 IC=(0.1-0.05+0.4)/4=0.1125>0；3 折中 2 折同号
    assert metrics["ic_mean"] == pytest.approx(0.1125)
    assert metrics["sign_consistency"] == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    ("train_ic", "wf_ic", "expected"),
    [
        (0.25, -0.2, "sign_flip"),
        (0.30, 0.10, "weak"),
        (0.20, 0.15, "ok"),
        (-0.20, -0.15, "ok"),
    ],
)
def test_aggregate_wf_flag_matches_single_shot_rule(train_ic, wf_ic, expected):
    folds = [_fold(0, wf_ic)]
    _, flag, _ = FactorService._aggregate_wf(folds, train_ic)
    assert flag == expected


def test_aggregate_wf_skips_none_folds_and_notes_shortfall():
    folds = [_fold(0, 0.2), _fold(1, None, bar_count=6), _fold(2, None, bar_count=6)]
    metrics, flag, note = FactorService._aggregate_wf(folds, 0.2)
    assert metrics["valid_folds"] == 1
    assert metrics["n_folds"] == 3
    assert metrics["ic_mean"] == pytest.approx(0.2)
    # 单折无法估计折间离散度 → std/ir 为 None；符号一致性按唯一有效折计为 1
    assert metrics["ic_std"] is None
    assert metrics["ic_ir"] is None
    assert metrics["sign_consistency"] == 1.0
    assert flag == "ok"
    assert note is not None and "2/3" in note


def test_aggregate_wf_all_empty_folds_yields_none_ic():
    folds = [_fold(0, None, bar_count=4), _fold(1, None, bar_count=4), _fold(2, None, bar_count=4)]
    metrics, flag, note = FactorService._aggregate_wf(folds, 0.2)
    assert metrics["ic_mean"] is None
    assert metrics["ic_std"] is None
    assert metrics["ic_ir"] is None
    assert metrics["sign_consistency"] is None
    assert metrics["valid_folds"] == 0
    assert flag is None
    assert note is not None and "3/3" in note


def test_aggregate_wf_none_train_ic_gives_none_flag():
    folds = [_fold(0, 0.2)]
    metrics, flag, _note = FactorService._aggregate_wf(folds, None)
    assert metrics["ic_mean"] == pytest.approx(0.2)
    assert flag is None


# ---------------------------------------------------------------------------
# 6) 短数据：不抛异常，折 IC 为 None，汇总带 n_folds 与 oos_note
# ---------------------------------------------------------------------------


def test_short_data_does_not_raise_and_marks_folds_insufficient(service):
    # n=60、k=6：OOS 仅 18 个时间点，每折 3 个时间点、前瞻 dropna 后 2 个 <3 → IC 全空
    raw_map = make_raw_map(n=60)
    result = service.analyze_code_panel(MOM_CODE, raw_map, interval="1h", wf_folds=6, test_ratio=0.3, label="short")
    assert result["train"] is not None
    wf = result["wf"]
    assert wf is not None
    assert wf["n_folds"] == 6
    assert wf["valid_folds"] == 0
    assert wf["ic_mean"] is None
    assert wf["oos_flag"] is None
    assert wf["oos_note"] is not None and "6/6" in wf["oos_note"]
    # ic_mean 为 None 的折仍如实返回 bar_count
    assert all(isinstance(f["bar_count"], int) for f in wf["folds"])
