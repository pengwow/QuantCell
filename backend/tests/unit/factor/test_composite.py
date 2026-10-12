# 合成因子（IC 加权 zscore）：
# 纯函数（fit_ic_weights/_fit_ts_stats/_normalize_panel/build_composite）
# + save/delete 持久化 + 名称互斥/成分约束/恶意成分拦截
import json

import numpy as np
import pandas as pd
import pytest

from factor.sandbox import SandboxSecurityError
from factor.service import FactorError, FactorService

CODE_MOM = 'factor = df["close"].pct_change(5)'
CODE_VOL_MOM = 'factor = df["volume"].pct_change(5)'


# ---------------------------------------------------------------------------
# 合成数据 Provider
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


def _mi_panel(mapping: dict[str, list[float]], start="2026-01-01") -> pd.Series:
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
    assert stats["A"]["std"] == pytest.approx(1.0)
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
    panel = _mi_panel({"A": [10.0, 12.0, 8.0]})
    ts_stats = {"A": {"mean": 10.0, "std": 2.0}}
    out = FactorService._normalize_panel(panel, ts_stats)
    assert out.tolist() == pytest.approx([0.0, 1.0, -1.0])


def test_normalize_time_series_zero_std_no_crash():
    panel = _mi_panel({"A": [3.0, 3.0]})
    out = FactorService._normalize_panel(panel, {"A": {"mean": 3.0, "std": 0.0}})
    assert out.tolist() == [0.0, 0.0]


def test_normalize_unseen_symbol_uses_panel_history_fallback():
    panel = _mi_panel({"X": [10.0, 12.0, 8.0]})
    out = FactorService._normalize_panel(panel, {})
    assert out.tolist() == pytest.approx([0.0, 1.0, -1.0])


def test_normalize_winsorizes_large_cross_section():
    vals = [*np.linspace(0.0, 10.0, 199), 1000.0]
    panel = _mi_panel({f"S{i:03d}": [v] for i, v in enumerate(vals)})
    out = FactorService._normalize_panel(panel, {})
    z = sorted(out.tolist())
    assert z[-1] < 2.5
    assert z[0] > -2.5


def test_normalize_small_cross_section_skips_winsorize():
    panel = _mi_panel({"A": [1.0], "B": [1.0], "C": [100.0]})
    out = FactorService._normalize_panel(panel, {})
    z = sorted(out.tolist())
    assert z[-1] > 1.15


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
    a = _mi_panel({"A": [1.0], "B": [2.0], "C": [3.0]})
    b = pd.concat(
        [
            _mi_panel({"A": [3.0], "B": [2.0], "C": [1.0]}),
            _mi_panel({"A": [12.0]}, start="2026-01-02"),
        ]
    ).sort_index()
    ts_stats = [{}, {"A": {"mean": 10.0, "std": 2.0}}]
    out = FactorService.build_composite([a, b], [1.0, -1.0], ts_stats)
    t1 = out.xs(pd.Timestamp("2026-01-02"), level=0)
    assert len(t1) == 1
    assert t1.iloc[0] == pytest.approx(-1.0)
    assert len(out.xs(pd.Timestamp("2026-01-01"), level=0)) == 3


# ---------------------------------------------------------------------------
# 5) 持久化往返 + 名称互斥 + 成分约束
# ---------------------------------------------------------------------------


def _simple_ts_stats(symbols):
    return {s: {"mean": 0.0, "std": 1.0} for s in symbols}


def test_save_composite_persistence_roundtrip(svc):
    name = "llm_comp_demo"
    svc.save_composite(
        name,
        "演示合成",
        [CODE_MOM, CODE_VOL_MOM],
        [0.6, -0.4],
        [_simple_ts_stats(["BTCUSDT"]), _simple_ts_stats(["BTCUSDT"])],
        TRAIN_WINDOW,
        provenance={"source": "llm_mining"},
    )

    spec = svc._composite_map.get(name)
    assert spec["method"] == "ic_zscore_v1"
    assert spec["train_window"] == TRAIN_WINDOW
    assert len(spec["constituents"]) == 2
    assert spec["constituents"][0]["code"] == CODE_MOM
    assert spec["provenance"] == {"source": "llm_mining"}

    assert name in svc.get_factor_list()
    details = {d["name"]: d for d in svc.get_factor_details()}
    assert details[name]["kind"] == "composite"
    assert details[name]["category"] == "llm_composite"
    assert details[name]["constituents_count"] == 2


def test_delete_composite(svc):
    svc.save_composite(
        "llm_comp_del",
        "",
        [CODE_MOM, CODE_VOL_MOM],
        [0.5, -0.5],
        [_simple_ts_stats(["BTCUSDT"]), _simple_ts_stats(["BTCUSDT"])],
        TRAIN_WINDOW,
    )
    assert svc.delete_composite("llm_comp_del") is True
    assert "llm_comp_del" not in svc.get_factor_list()
    with pytest.raises(FactorError):
        svc.delete_composite("llm_comp_del")


def test_save_composite_rejects_name_collisions(svc):
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
    with pytest.raises(FactorError):
        svc.save_composite("close", **args)
    svc.add_factor("my_expr_x", "close - open")
    with pytest.raises(FactorError):
        svc.save_composite("my_expr_x", **args)
    svc.save_code_factor("llm_code_x", CODE_MOM)
    with pytest.raises(FactorError):
        svc.save_composite("llm_code_x", **args)
    with pytest.raises(FactorError):
        svc.save_composite("1bad", **args)
    svc.save_composite("llm_comp_x", **args)
    with pytest.raises(FactorError):
        svc.add_factor("llm_comp_x", "close - open")


def test_save_composite_same_name_overwrite_allowed(svc):
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
    assert svc.save_composite("llm_comp_same", **common) is True
    common["description"] = "改名说明"
    assert svc.save_composite("llm_comp_same", **common) is True
    assert svc._composite_map["llm_comp_same"]["description"] == "改名说明"


def test_save_composite_validates_constituent_count(svc):
    with pytest.raises(FactorError):
        svc.save_composite(
            "llm_comp_few",
            "",
            [CODE_MOM],
            [1.0],
            [_simple_ts_stats(["BTCUSDT"])],
            TRAIN_WINDOW,
        )


def test_save_composite_rejects_malicious_constituent(svc, monkeypatch):
    # 还原真实沙箱校验（svc fixture 默认 mock 了 validate）
    from factor.sandbox import FactorSandbox

    monkeypatch.setattr(svc._sandbox, "validate", FactorSandbox().validate)
    with pytest.raises(SandboxSecurityError):
        svc.save_composite(
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
    assert "llm_comp_evil" not in svc._composite_map
