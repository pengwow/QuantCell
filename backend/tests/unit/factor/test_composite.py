# 合成因子（IC 加权 zscore）：
# 纯函数（fit_ic_weights/_fit_ts_stats/_normalize_panel/build_composite）
# + analyze_composite 三路径与沙箱计数 + 持久化往返/名称互斥/恶意成分拦截
import json

import numpy as np
import pandas as pd
import pytest

from factor.code_store import CodeFactorStore
from factor.composite_store import CompositeFactorStore
from factor.sandbox import FactorSandbox, SandboxSecurityError
from factor.service import FactorError, FactorService

CODE_MOM = 'factor = df["close"].pct_change(5)'
CODE_VOL_MOM = 'factor = df["volume"].pct_change(5)'


# ---------------------------------------------------------------------------
# 合成数据 Provider（与 test_llm_miner.Provider / test_walk_forward 同构）
# ---------------------------------------------------------------------------


class Provider:
    def __init__(self, n=240):
        self.frames = {}
        for k, sym in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
            r = np.random.default_rng(10 + k)
            close = 100 + np.cumsum(r.normal(0, 1, n))
            ts = pd.date_range("2026-01-01", periods=n, freq="1h")
            close = close + np.arange(n) * (0.01 * (k + 1))
            self.frames[sym] = pd.DataFrame(
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

    def get_kline_data(self, symbol, interval, candle_type, start, end, columns=None):
        return self.frames[symbol].copy()


@pytest.fixture
def service(tmp_path):
    return FactorService(
        code_store=CodeFactorStore(tmp_path / "c.json"),
        composite_store=CompositeFactorStore(tmp_path / "comp.json"),
        sandbox=FactorSandbox(),
    )


def _mi_panel(mapping: dict[str, list[float]], start="2026-01-01") -> pd.Series:
    """{symbol: 值列表} -> MultiIndex(datetime,symbol) 面板（允许 NaN）。"""
    frames = []
    for sym, vals in mapping.items():
        idx = pd.MultiIndex.from_arrays(
            [pd.date_range(start, periods=len(vals), freq="1h"), [sym] * len(vals)],
            names=["datetime", "symbol"],
        )
        frames.append(pd.Series(vals, index=idx, dtype=float))
    return pd.concat(frames).sort_index()


TRAIN_WINDOW = {
    "start": "2026-01-01T00:00:00",
    "end": "2026-01-07T23:00:00",
    "interval": "1h",
    "candle_type": "spot",
}


# ---------------------------------------------------------------------------
# 1) fit_ic_weights
# ---------------------------------------------------------------------------


def test_fit_ic_weights_signed_and_abs_sum_one():
    w = FactorService.fit_ic_weights([0.1, -0.2, None])
    assert w is not None
    assert w[0] == pytest.approx(1 / 3)
    assert w[1] == pytest.approx(-2 / 3)
    assert w[2] is None
    # 带符号、绝对值和归一为 1
    assert sum(abs(x) for x in w if x is not None) == pytest.approx(1.0)


def test_fit_ic_weights_single_none_input_returns_none():
    assert FactorService.fit_ic_weights([0.1, None]) is None
    assert FactorService.fit_ic_weights([0.1]) is None
    assert FactorService.fit_ic_weights([]) is None


def test_fit_ic_weights_zero_denominator_returns_none():
    assert FactorService.fit_ic_weights([0.0, -0.0]) is None


# ---------------------------------------------------------------------------
# 2) _fit_ts_stats
# ---------------------------------------------------------------------------


def test_fit_ts_stats_per_symbol_plain_floats():
    panel = _mi_panel({"A": [1.0, 2, 3], "B": [10.0]})
    stats = FactorService._fit_ts_stats(panel)
    assert set(stats) == {"A", "B"}
    assert stats["A"]["mean"] == pytest.approx(2.0)
    assert stats["A"]["std"] == pytest.approx(1.0)  # pandas ddof=1
    # 单点无法估计 std → 兜底 1.0；全部为普通 float，可 JSON 序列化
    assert stats["B"]["mean"] == 10.0
    assert stats["B"]["std"] == 1.0
    json.dumps(stats)


def test_fit_ts_stats_zero_std_falls_back_to_one():
    panel = _mi_panel({"A": [5.0, 5, 5]})
    stats = FactorService._fit_ts_stats(panel)
    assert stats["A"]["mean"] == 5.0
    assert stats["A"]["std"] == 1.0


# ---------------------------------------------------------------------------
# 3) _normalize_panel
# ---------------------------------------------------------------------------


def test_normalize_cross_section_three_symbols_hand_values():
    # 同一时刻 3 品种（>=3 走截面路径）：总体 zscore（ddof=0）
    panel = _mi_panel({"A": [1.0], "B": [2.0], "C": [3.0]})
    out = FactorService._normalize_panel(panel, {})
    by_sym = {idx[1]: v for idx, v in out.items()}
    std = np.sqrt(2 / 3)
    assert by_sym["A"] == pytest.approx(-1 / std)
    assert by_sym["B"] == pytest.approx(0.0)
    assert by_sym["C"] == pytest.approx(1 / std)


def test_normalize_cross_section_constant_row_is_zero():
    panel = _mi_panel({"A": [7.0], "B": [7.0], "C": [7.0]})
    out = FactorService._normalize_panel(panel, {})
    assert sorted(out.tolist()) == [0.0, 0.0, 0.0]


def test_normalize_time_series_path_uses_frozen_ts_stats():
    # 单品种每个时刻截面不足 3 → 走冻结 ts_stats 的时序 zscore
    panel = _mi_panel({"A": [10.0, 12.0, 8.0]})
    ts_stats = {"A": {"mean": 10.0, "std": 2.0}}
    out = FactorService._normalize_panel(panel, ts_stats)
    assert out.tolist() == pytest.approx([0.0, 1.0, -1.0])


def test_normalize_time_series_zero_std_no_crash():
    panel = _mi_panel({"A": [3.0, 3.0]})
    out = FactorService._normalize_panel(panel, {"A": {"mean": 3.0, "std": 0.0}})
    assert out.tolist() == [0.0, 0.0]


def test_normalize_unseen_symbol_uses_panel_history_fallback():
    # ts_stats 不含该 symbol（train 未见品种的罕见兜底）：用本面板全历史 mean/std
    panel = _mi_panel({"X": [10.0, 12.0, 8.0]})  # 单品种 → 时序路径
    out = FactorService._normalize_panel(panel, {})
    # mean=10, std(ddof=1)=2
    assert out.tolist() == pytest.approx([0.0, 1.0, -1.0])


def test_normalize_winsorizes_large_cross_section():
    # 200 品种（>=10 触发 winsorize）：199 个密集 0-10 值 + 1 个 1000 极端值。
    # 极端值被 clip 到 99% 分位（≈9.9）后 z 落入正常区间；不 clip 时 z≈30+
    vals = [*np.linspace(0.0, 10.0, 199), 1000.0]
    panel = _mi_panel({f"S{i:03d}": [v] for i, v in enumerate(vals)})
    out = FactorService._normalize_panel(panel, {})
    z = sorted(out.tolist())
    assert z[-1] < 2.5
    assert z[0] > -2.5  # 低端密集值不被极端值拉动


def test_normalize_small_cross_section_skips_winsorize():
    # 3 品种（<10）不做 winsorize：极端值原样保留
    panel = _mi_panel({"A": [1.0], "B": [1.0], "C": [100.0]})
    out = FactorService._normalize_panel(panel, {})
    z = sorted(out.tolist())
    assert z[-1] > 1.15  # sqrt(2)/... 未裁剪的极端 z


# ---------------------------------------------------------------------------
# 4) build_composite
# ---------------------------------------------------------------------------


def test_build_composite_hand_computed_opposite_panels():
    a = _mi_panel({"A": [1.0], "B": [2.0], "C": [3.0]})
    b = _mi_panel({"A": [3.0], "B": [2.0], "C": [1.0]})
    out = FactorService.build_composite([a, b], [1.0, -1.0], [{}, {}])
    std = np.sqrt(2 / 3)
    by_sym = {idx[1]: v for idx, v in out.items()}
    assert by_sym["A"] == pytest.approx(-2 / std)
    assert by_sym["B"] == pytest.approx(0.0)
    assert by_sym["C"] == pytest.approx(2 / std)


def test_build_composite_union_index_missing_constituent_zero_contribution():
    # A 面板只有 t0 三品种；B 面板多一个 t1 单品种行
    a = _mi_panel({"A": [1.0], "B": [2.0], "C": [3.0]})
    b = pd.concat(
        [
            _mi_panel({"A": [3.0], "B": [2.0], "C": [1.0]}),
            _mi_panel({"A": [12.0]}, start="2026-01-02"),
        ]
    ).sort_index()
    ts_stats = [{}, {"A": {"mean": 10.0, "std": 2.0}}]
    out = FactorService.build_composite([a, b], [1.0, -1.0], ts_stats)
    # t1：A 成分缺失记 0 贡献；B 归一为 (12-10)/2=1，权重 -1 → -1
    t1 = out.xs(pd.Timestamp("2026-01-02"), level=0)
    assert len(t1) == 1
    assert t1.iloc[0] == pytest.approx(-1.0)
    # t0 三行照常
    assert len(out.xs(pd.Timestamp("2026-01-01"), level=0)) == 3


# ---------------------------------------------------------------------------
# 5) analyze_composite：train / 单次切分 / walk-forward
# ---------------------------------------------------------------------------


def _fitted_weights_and_stats(service, raw_map, *, test_ratio=0.0, wf_folds=0):
    """对两个成分各跑一次 analyze_code_panel，拟合 train IC 权重与 ts_stats。"""
    codes = [CODE_MOM, CODE_VOL_MOM]
    panels_analysis = [
        service.analyze_code_panel(code, raw_map, interval="1h", test_ratio=test_ratio, wf_folds=wf_folds)
        for code in codes
    ]
    ics = [a["train"]["ic"]["mean"] for a in panels_analysis]
    weights = FactorService.fit_ic_weights(ics)
    ts_stats = [FactorService._fit_ts_stats(a["train_factor"]) for a in panels_analysis]
    return codes, weights, ts_stats, ics


def test_analyze_composite_train_only(service):
    raw_map = Provider().frames
    codes, weights, ts_stats, _ics = _fitted_weights_and_stats(service, raw_map)
    assert weights is not None
    res = service.analyze_composite(codes, weights, ts_stats, raw_map, interval="1h", test_ratio=0)
    assert set(res) == {"train", "test", "wf"}
    assert res["test"] is None and res["wf"] is None
    train = res["train"]
    assert train["bar_count"] > 0
    assert train["ic"]["mean"] is not None
    assert "inspection" in train


def test_analyze_composite_single_split_runs_two_n_sandboxes(service, monkeypatch):
    raw_map = Provider().frames
    codes, weights, ts_stats, _ics = _fitted_weights_and_stats(service, raw_map, test_ratio=0.3)
    original_run = service._sandbox.run
    calls = []

    def spy(code, frames):
        calls.append(len(next(iter(frames.values()))))
        return original_run(code, frames)

    monkeypatch.setattr(service._sandbox, "run", spy)
    res = service.analyze_composite(codes, weights, ts_stats, raw_map, interval="1h", test_ratio=0.3)
    # 2 成分 × (train+test) = 4 次；train=168 行、test=72 行各两轮
    assert calls == [168, 168, 72, 72]
    assert res["test"] is not None
    assert res["test"]["bar_count"] > 0


def test_analyze_composite_wf_runs_n_times_one_plus_k(service, monkeypatch):
    raw_map = Provider().frames
    # 用 wf 路径的 train 段（168 行前缀）拟合冻结参数；权重只要求结构合法
    codes = [CODE_MOM, CODE_VOL_MOM]
    train_map, _ = FactorService._split_raw_map(raw_map, 0.3)
    ts_stats = []
    for code in codes:
        panel = service.assemble_code_panel("c", service._sandbox.run(code, train_map), train_map)
        ts_stats.append(FactorService._fit_ts_stats(panel))
    weights = [0.6, -0.4]

    original_run = service._sandbox.run
    calls = []

    def spy(code, frames):
        calls.append(len(next(iter(frames.values()))))
        return original_run(code, frames)

    monkeypatch.setattr(service._sandbox, "run", spy)
    res = service.analyze_composite(codes, weights, ts_stats, raw_map, interval="1h", test_ratio=0.3, wf_folds=3)
    # n 成分 × (1 train + 3 折) = 8 次独立沙箱执行
    assert len(calls) == 2 * (1 + 3)
    # 每折先两成分同长度前缀（train 168，折前缀 192/216/240）
    assert sorted(calls) == sorted([168, 168, 192, 192, 216, 216, 240, 240])
    wf = res["wf"]
    assert wf is not None and res["test"] is None
    assert len(wf["folds"]) == 3
    assert wf["n_folds"] == 3
    assert [f["bar_count"] for f in wf["folds"]] == [69, 69, 69]
    assert wf["bar_count"] == 207
    assert wf["oos_flag"] in {"ok", "weak", "sign_flip", None}


# ---------------------------------------------------------------------------
# 6) 持久化往返：save → store spec → factor_name 路由结果一致
# ---------------------------------------------------------------------------


def _simple_ts_stats(symbols):
    return {s: {"mean": 0.0, "std": 1.0} for s in symbols}


def test_save_composite_persistence_roundtrip_and_panel_route(service):
    raw_map = Provider().frames
    codes, weights, ts_stats, _ = _fitted_weights_and_stats(service, raw_map)
    name = "llm_comp_demo"
    service.save_composite(
        name,
        "演示合成",
        codes,
        weights,
        ts_stats,
        TRAIN_WINDOW,
        provenance={"source": "llm_mining"},
    )

    # store 内 spec 结构完整
    spec = service._composite_store.get(name)
    assert spec["method"] == "ic_zscore_v1"
    assert spec["train_window"] == TRAIN_WINDOW
    assert len(spec["constituents"]) == 2
    assert spec["constituents"][0]["code"] == codes[0]
    assert spec["provenance"] == {"source": "llm_mining"}

    # 列表/详情纳入
    assert name in service.get_factor_list()
    details = {d["name"]: d for d in service.get_factor_details()}
    assert details[name]["kind"] == "composite"
    assert details[name]["category"] == "llm_composite"
    assert details[name]["constituents_count"] == 2

    # 面板路由结果与按冻结 spec 直接组合完全一致
    routed = service._panel_from_raw(name, raw_map)
    direct_panels = [
        service.assemble_code_panel(f"c{i}", service._sandbox.run(code, raw_map), raw_map)
        for i, code in enumerate(codes)
    ]
    expected = FactorService.build_composite(direct_panels, weights, ts_stats)
    pd.testing.assert_series_equal(routed, expected, check_names=False)

    # analyze 全链路可经 factor_name 直接访问（与 analyze_composite train 同口径）
    via_name = service.analyze(name, ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "1h", "spot", None, None, provider=Provider())
    direct = service.analyze_composite(codes, weights, ts_stats, raw_map, interval="1h")
    assert via_name["bar_count"] == direct["train"]["bar_count"]
    assert via_name["ic"]["mean"] == pytest.approx(direct["train"]["ic"]["mean"])


def test_composite_store_corrupt_json_loads_empty(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    store = CompositeFactorStore(path)
    assert store.all() == {}
    assert store.get("x") is None
    assert store.exists("x") is False


def test_delete_composite(service):
    service.save_composite(
        "llm_comp_del",
        "",
        [CODE_MOM, CODE_VOL_MOM],
        [0.5, -0.5],
        [_simple_ts_stats(["BTCUSDT"]), _simple_ts_stats(["BTCUSDT"])],
        TRAIN_WINDOW,
    )
    assert service.delete_composite("llm_comp_del") is True
    assert "llm_comp_del" not in service.get_factor_list()
    with pytest.raises(FactorError):
        service.delete_composite("llm_comp_del")
    # 通用 delete_factor 也能路由 composite
    service.save_composite(
        "llm_comp_del2",
        "",
        [CODE_MOM, CODE_VOL_MOM],
        [0.5, -0.5],
        [_simple_ts_stats(["BTCUSDT"]), _simple_ts_stats(["BTCUSDT"])],
        TRAIN_WINDOW,
    )
    assert service.delete_factor("llm_comp_del2") is True


# ---------------------------------------------------------------------------
# 7) 名称互斥 / 成分约束 / 恶意代码
# ---------------------------------------------------------------------------


def test_save_composite_rejects_name_collisions(service):
    args = dict(
        description="",
        codes=[CODE_MOM, CODE_VOL_MOM],
        weights=[0.5, -0.5],
        ts_stats_list=[
            _simple_ts_stats(["BTCUSDT"]),
            _simple_ts_stats(["BTCUSDT"]),
        ],
        train_window=TRAIN_WINDOW,
    )
    # 内置
    with pytest.raises(FactorError):
        service.save_composite("close", **args)
    # 表达式因子
    service.add_factor("my_expr_x", "close - open")
    with pytest.raises(FactorError):
        service.save_composite("my_expr_x", **args)
    # 代码因子
    service.save_code_factor("llm_code_x", CODE_MOM)
    with pytest.raises(FactorError):
        service.save_composite("llm_code_x", **args)
    # 非法名称
    with pytest.raises(FactorError):
        service.save_composite("1bad", **args)
    # 与表达式 add 反向互斥
    service.save_composite("llm_comp_x", **args)
    with pytest.raises(FactorError):
        service.add_factor("llm_comp_x", "close - open")


def test_save_composite_same_name_overwrite_allowed(service):
    common = dict(
        description="",
        codes=[CODE_MOM, CODE_VOL_MOM],
        weights=[0.5, -0.5],
        ts_stats_list=[
            _simple_ts_stats(["BTCUSDT"]),
            _simple_ts_stats(["BTCUSDT"]),
        ],
        train_window=TRAIN_WINDOW,
    )
    assert service.save_composite("llm_comp_same", **common) is True
    common["description"] = "改名说明"
    assert service.save_composite("llm_comp_same", **common) is True
    assert service._composite_store.get("llm_comp_same")["description"] == "改名说明"


def test_save_composite_validates_constituent_count(service):
    with pytest.raises(FactorError):
        service.save_composite(
            "llm_comp_few",
            "",
            [CODE_MOM],
            [1.0],
            [_simple_ts_stats(["BTCUSDT"])],
            TRAIN_WINDOW,
        )


def test_save_composite_rejects_malicious_constituent(service):
    with pytest.raises(SandboxSecurityError):
        service.save_composite(
            "llm_comp_evil",
            "",
            ["import os", CODE_MOM],
            [0.5, 0.5],
            [
                _simple_ts_stats(["BTCUSDT"]),
                _simple_ts_stats(["BTCUSDT"]),
            ],
            TRAIN_WINDOW,
        )
    # 被拒后不落库
    assert service._composite_store.exists("llm_comp_evil") is False
