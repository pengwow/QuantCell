# LLM 挖掘闭环测试：用 Fake backend 回放预置代码，覆盖成功/静态失败/运行失败/反思/去重
import json

import numpy as np
import pandas as pd
import pytest

import factor.llm_miner as miner
from factor.code_store import CodeFactorStore
from factor.engine import load_raw_ohlcv
from factor.llm_miner import LLMMineParams, correlation_dedup, oos_flag, run_llm_mining
from factor.sandbox import FactorSandbox
from factor.service import FactorService


class FakeBackend:
    """按调用顺序回放 content；记录消息供断言反思上下文。

    元素可为字符串（finish_reason=Stop）或 (content, finish_reason) 元组，
    用于模拟 reasoning 模型 finish=length 的空响应。
    """

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = []

    async def chat_async(self, messages):
        self.calls.append(messages)
        raw = self._contents[(len(self.calls) - 1) % len(self._contents)]
        content, finish_reason = raw if isinstance(raw, tuple) else (raw, "Stop")
        return {
            "content": content,
            "finish_reason": finish_reason,
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        }


class Provider:
    def __init__(self, n=240):
        import numpy as np
        import pandas as pd

        self.frames = {}
        for k, sym in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
            r = np.random.default_rng(10 + k)
            close = 100 + np.cumsum(r.normal(0, 1, n))
            ts = pd.date_range("2026-01-01", periods=n, freq="1h")
            # 注入一个可预测的截面结构，让简单动量有非零 IC
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
    return FactorService(code_store=CodeFactorStore(tmp_path / "c.json"), sandbox=FactorSandbox())


def _params(**kw):
    base = dict(
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        interval="1h",
        candle_type="spot",
        start=None,
        end=None,
        n_candidates=3,
        n_rounds=1,
        top_k=3,
        # 锁定旧用例的单段评估语义；样本外用例显式传 0.3
        test_ratio=0,
    )
    base.update(kw)
    return LLMMineParams(**base)


def test_mine_happy_path_with_success_and_security_failure(service):
    contents = [
        '```python\nfactor = df["close"].pct_change(5)\n```',
        "import os\nfactor = 1",  # 静态拒绝
        'factor = df["volume"] / df["volume"].rolling(20).mean()',
    ]
    result = run_llm_mining(_params(), backend=FakeBackend(contents), provider=Provider(), service=service)
    assert result["stats"]["generated"] == 3
    statuses = {c["status"] for c in result["candidates"]}
    assert "success" in statuses and "security_error" in statuses
    assert len(result["best"]) >= 1
    row = next(c for c in result["candidates"] if c["status"] == "success")
    assert row["metrics"]["fitness"] >= 0
    assert {"ic_mean", "coverage", "turnover", "ic_ir"} <= set(row["metrics"])
    assert row["code_hash"]


def test_mine_runtime_error_classified(service):
    contents = ['factor = df["close"] / df["missing_col"]']
    result = run_llm_mining(
        _params(n_candidates=1), backend=FakeBackend(contents), provider=Provider(), service=service
    )
    assert result["candidates"][0]["status"] == "runtime_error"
    assert result["candidates"][0]["error"]


def test_reflection_round_includes_prior_errors(service):
    backend = FakeBackend(
        [
            "import socket\nfactor=1",  # round1 全部静态失败
            'factor = df["close"].pct_change(3)',  # round2 成功
        ]
    )
    result = run_llm_mining(
        _params(n_candidates=1, n_rounds=2),
        backend=backend,
        provider=Provider(),
        service=service,
    )
    # round2 的 user 消息应包含 round1 错误摘要
    round2_user = backend.calls[1][-1]["content"]
    assert "上一轮" in round2_user or "反思" in round2_user
    assert any(c["round"] == 2 and c["status"] == "success" for c in result["candidates"])


def test_duplicate_code_deduped(service):
    code = 'factor = df["close"].pct_change(5)'
    result = run_llm_mining(
        _params(n_candidates=3),
        backend=FakeBackend([code, code, code]),
        provider=Provider(),
        service=service,
    )
    assert result["stats"]["unique"] == 1
    assert len(result["candidates"]) == 1


def test_empty_llm_content_skipped(service):
    result = run_llm_mining(
        _params(n_candidates=2),
        backend=FakeBackend(["", "   "]),
        provider=Provider(),
        service=service,
    )
    assert result["stats"]["generated"] == 2
    assert all(c["status"] == "empty" for c in result["candidates"])


def test_length_finish_with_empty_content_marked_truncated(service):
    """reasoning 模型思考耗尽预算（finish=length, content 空）必须区别于普通空响应。"""
    result = run_llm_mining(
        _params(n_candidates=1),
        backend=FakeBackend([("", "Length")]),
        provider=Provider(),
        service=service,
    )
    row = result["candidates"][0]
    assert row["status"] == "llm_truncated"
    assert "token" in row["error"]
    assert result["stats"]["succeeded"] == 0


def test_progress_callback_called(service):
    seen = []
    run_llm_mining(
        _params(n_candidates=1),
        backend=FakeBackend(['factor = df["close"].pct_change(2)']),
        provider=Provider(),
        service=service,
        progress=lambda p, s, m: seen.append((round(p, 1), s)),
    )
    assert seen[0][0] < seen[-1][0]


# ---------------------------------------------------------------------------
# 样本外（train/test 切分）复核
# ---------------------------------------------------------------------------


def test_split_raw_map_cuts_by_global_time_cutoff_per_symbol():
    import pandas as pd

    n = 240
    raw_map = Provider(n=n).frames
    train_map, test_map = FactorService._split_raw_map(raw_map, 0.3)

    # 同起点同长度品种：全局时间切点等价于 168/72 行切，且各品种共用同一 cutoff
    for symbol, raw in raw_map.items():
        assert len(train_map[symbol]) == 168
        assert len(test_map[symbol]) == 72
        pd.testing.assert_frame_equal(train_map[symbol], raw.iloc[:168].copy())
        pd.testing.assert_frame_equal(test_map[symbol], raw.iloc[168:].copy())
        # 后段首行时间严格晚于前段末行
        assert test_map[symbol]["timestamp"].iloc[0] > train_map[symbol]["timestamp"].iloc[-1]

    # 各品种 test 窗口时间范围必须一致（全局切点，而非各自行数比例）
    test_starts = {s: df["timestamp"].iloc[0] for s, df in test_map.items()}
    test_ends = {s: df["timestamp"].iloc[-1] for s, df in test_map.items()}
    assert len(set(test_starts.values())) == 1
    assert len(set(test_ends.values())) == 1


def test_split_raw_map_aligns_test_windows_when_histories_differ():
    """不同历史长度（起点不同、终点相近）时，test 窗口必须时间对齐。

    回归：逐品种按行数切会让短历史品种 test 窗口整体偏晚、与长历史品种
    几乎不重叠，导致截面 IC 没有同日配对（真实 BTC/ETH 数据暴露的缺陷）。
    """
    import pandas as pd

    end = pd.Timestamp("2026-10-01 00:00:00")
    long_ts = pd.date_range(end=end, periods=1008, freq="1h")
    short_ts = pd.date_range(end=end, periods=744, freq="1h")

    def frame(ts):
        return pd.DataFrame(
            {
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
                "quote_volume": 1.0,
                "timestamp": ts.astype("int64"),
            }
        )

    raw_map = {"BTCUSDT": frame(long_ts), "ETHUSDT": frame(short_ts)}
    train_map, test_map = FactorService._split_raw_map(raw_map, 0.3)

    btc_start = test_map["BTCUSDT"]["timestamp"].iloc[0]
    eth_start = test_map["ETHUSDT"]["timestamp"].iloc[0]
    # 两品种 test 起点是同一时间戳（全局切点），而不是各自 70% 行位
    assert btc_start == eth_start
    # test 段必须有大量同日配对（>90% 较短 test 段），截面 IC 才有效
    overlap = len(set(test_map["BTCUSDT"]["timestamp"]) & set(test_map["ETHUSDT"]["timestamp"]))
    assert overlap >= 0.9 * min(len(test_map["BTCUSDT"]), len(test_map["ETHUSDT"]))
    # train/test 时间不交叉
    for symbol in raw_map:
        assert train_map[symbol]["timestamp"].max() < test_map[symbol]["timestamp"].min()


def test_split_raw_map_ratio_zero_returns_original_and_empty_test():
    raw_map = Provider(n=240).frames
    train_map, test_map = FactorService._split_raw_map(raw_map, 0.0)
    assert test_map == {}
    # ratio=0 不复制，train 就是原对象（退化为全量评估）
    assert train_map is raw_map


def test_split_raw_map_does_not_mutate_input_frames():
    raw_map = Provider(n=240).frames
    FactorService._split_raw_map(raw_map, 0.3)
    assert all(len(df) == 240 for df in raw_map.values())


def test_mine_test_ratio_zero_has_no_oos_fields(service):
    contents = ['factor = df["close"].pct_change(5)']
    result = run_llm_mining(
        _params(n_candidates=1, test_ratio=0),
        backend=FakeBackend(contents),
        provider=Provider(),
        service=service,
    )
    row = result["candidates"][0]
    assert row["status"] == "success"
    assert row["metrics_oos"] is None
    assert row["oos_flag"] is None
    assert row["oos_note"] is None
    assert result["stats"]["test_ratio"] == 0


def test_mine_test_ratio_runs_sandbox_twice_and_emits_oos_metrics(service, monkeypatch):
    contents = ['factor = df["close"].pct_change(5)']
    original_run = service._sandbox.run
    segment_rows = []

    def spy(code, frames):
        # 记录每次沙箱执行收到的首品种行数（train=168 / test=72）
        segment_rows.append(len(next(iter(frames.values()))))
        return original_run(code, frames)

    monkeypatch.setattr(service._sandbox, "run", spy)

    result = run_llm_mining(
        _params(n_candidates=1, test_ratio=0.3),
        backend=FakeBackend(contents),
        provider=Provider(),
        service=service,
    )
    row = result["candidates"][0]
    assert row["status"] == "success"
    # 每候选 train/test 独立沙箱执行各一次，禁止全量结果上切
    assert segment_rows == [168, 72]
    assert {"ic_mean", "coverage", "fitness", "bar_count"} <= set(row["metrics"])
    assert row["metrics_oos"] is not None
    assert {"ic_mean", "coverage", "fitness", "bar_count"} <= set(row["metrics_oos"])
    # test 段 bar 数明显少于 train 段
    assert row["metrics_oos"]["bar_count"] < row["metrics"]["bar_count"]
    assert row["oos_flag"] in {"ok", "weak", "sign_flip"}
    assert result["stats"]["test_ratio"] == 0.3


def test_mine_insufficient_oos_segment_keeps_success_with_note(service):
    # n=60、window=30：train=42 行（有效 37 >= 32）可分析；test=18 行（有效 13 < 32）不足
    contents = ['factor = df["close"].pct_change(5)']
    result = run_llm_mining(
        _params(symbols=["BTCUSDT"], n_candidates=1, test_ratio=0.3, window=30),
        backend=FakeBackend(contents),
        provider=Provider(n=60),
        service=service,
    )
    row = result["candidates"][0]
    assert row["status"] == "success"
    assert row["metrics"] is not None
    assert row["metrics_oos"] is None
    assert row["oos_flag"] is None
    assert row["oos_note"] == "样本外数据不足，未做复核"


@pytest.mark.parametrize(
    ("train_ic", "test_ic", "expected_flag"),
    [
        (0.10, -0.08, "sign_flip"),  # 符号反转
        (0.20, 0.05, "weak"),  # 衰减超半
        (0.20, 0.15, "ok"),  # 稳定
        (-0.20, -0.15, "ok"),  # 稳定（双侧同向）
    ],
)
def test_oos_flag_table(train_ic, test_ic, expected_flag):
    flag, note = oos_flag({"ic_mean": train_ic}, {"ic_mean": test_ic})
    assert flag == expected_flag
    if expected_flag == "ok":
        assert note == ""
    else:
        assert note


def test_mine_walk_forward_row_structure_and_stats(service, monkeypatch):
    """wf_folds=3：metrics_oos 为多折汇总（folds/sign_consistency/n_folds），沙箱 1+3 次。"""
    contents = ['factor = df["close"].pct_change(5)']
    original_run = service._sandbox.run
    calls = []

    def spy(code, frames):
        calls.append(len(next(iter(frames.values()))))
        return original_run(code, frames)

    monkeypatch.setattr(service._sandbox, "run", spy)

    result = run_llm_mining(
        _params(n_candidates=1, test_ratio=0.3, wf_folds=3),
        backend=FakeBackend(contents),
        provider=Provider(),
        service=service,
    )
    row = result["candidates"][0]
    assert row["status"] == "success"
    assert len(calls) == 4  # 1(train) + 3 折，禁止全量结果上切片
    mo = row["metrics_oos"]
    assert mo is not None
    assert len(mo["folds"]) == 3
    assert mo["n_folds"] == 3
    assert mo["valid_folds"] == 3
    assert {"ic_mean", "ic_ir", "coverage", "bar_count", "sign_consistency"} <= set(mo)
    assert mo["ic_mean"] is not None
    assert 0 <= mo["sign_consistency"] <= 1
    assert row["oos_flag"] in {"ok", "weak", "sign_flip"}
    assert result["stats"]["wf_folds"] == 3
    assert result["stats"]["test_ratio"] == 0.3


def test_mine_wf_folds_defaults_to_zero_in_stats(service):
    contents = ['factor = df["close"].pct_change(5)']
    result = run_llm_mining(
        _params(n_candidates=1),
        backend=FakeBackend(contents),
        provider=Provider(),
        service=service,
    )
    assert result["stats"]["wf_folds"] == 0


@pytest.mark.parametrize(
    ("train_metrics", "test_metrics"),
    [
        (None, None),
        ({"ic_mean": 0.1}, None),
        (None, {"ic_mean": 0.1}),
        ({"ic_mean": None}, {"ic_mean": 0.1}),
        ({"ic_mean": 0.1}, {"ic_mean": None}),
    ],
)
def test_oos_flag_returns_none_when_either_side_missing(train_metrics, test_metrics):
    assert oos_flag(train_metrics, test_metrics) == (None, None)


# ---------------------------------------------------------------------------
# 候选 train 段因子相关性去重（spearman 秩次一致度 + 贪心 fitness 排序）
# ---------------------------------------------------------------------------

CODE_MOM = 'factor = df["close"].pct_change(5)'
# 与 CODE_MOM 秩完全相同的单调变换（*、+、浮点常量 BinOp 均在沙箱白名单内）
CODE_MOM_SCALED = 'factor = df["close"].pct_change(5) * 100.0 + 3.0'
# Provider 合成数据下与价格动量近乎独立的成交量动量
CODE_VOL_MOM = 'factor = df["volume"].pct_change(5)'


def _mi_panel(mapping: dict[str, list[float]]) -> pd.Series:
    """{symbol: 值列表} -> MultiIndex(datetime,symbol) 面板（允许 NaN）。"""
    frames = []
    for sym, vals in mapping.items():
        idx = pd.MultiIndex.from_arrays(
            [pd.date_range("2026-01-01", periods=len(vals), freq="1h"), [sym] * len(vals)],
            names=["datetime", "symbol"],
        )
        frames.append(pd.Series(vals, index=idx, dtype=float))
    return pd.concat(frames).sort_index()


def test_factor_corr_scale_invariant_same_rank_is_one():
    # 两品种尺度差 1000 倍但组内秩相同 -> 各品种内部秩次一致度 ≈ 1
    base = np.random.default_rng(0).normal(size=40)
    s1 = _mi_panel({"BTCUSDT": base, "ETHUSDT": base * 2.0 + 5.0})
    s2 = _mi_panel({"BTCUSDT": base * 1000.0, "ETHUSDT": base * 0.001})
    corr = miner._factor_corr(s1, s2)
    assert corr is not None
    assert abs(corr) > 0.999


def test_factor_corr_anti_correlated_is_minus_one():
    s = _mi_panel({"BTCUSDT": np.random.default_rng(1).normal(size=40)})
    corr = miner._factor_corr(s, -s)
    assert corr is not None
    assert corr < -0.999


def test_factor_corr_returns_none_when_pairs_insufficient():
    # 短序列：配对 10 < min_pairs=30
    short_a = _mi_panel({"BTCUSDT": [1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
    short_b = _mi_panel({"BTCUSDT": [2.0, 4, 6, 8, 10, 12, 14, 16, 18, 20]})
    assert miner._factor_corr(short_a, short_b) is None
    # 时间不重叠：交集配对 0
    idx = pd.date_range("2026-01-01", periods=40, freq="1h")
    later_idx = pd.date_range("2026-03-01", periods=40, freq="1h")
    s1 = pd.Series(
        np.arange(40, dtype=float),
        index=pd.MultiIndex.from_arrays([idx, ["BTCUSDT"] * 40], names=["datetime", "symbol"]),
    )
    s2 = pd.Series(
        np.arange(40, dtype=float),
        index=pd.MultiIndex.from_arrays([later_idx, ["BTCUSDT"] * 40], names=["datetime", "symbol"]),
    )
    assert miner._factor_corr(s1, s2) is None


def test_train_factor_panel_exposed_on_analysis(service):
    """analyze_code_panel 透出 train 段 MultiIndex 因子面板（内部字段，挖掘结果里剥离）。"""
    raw_map = Provider().frames
    result = service.analyze_code_panel(CODE_MOM, raw_map, interval="1h", test_ratio=0)
    assert set(result) == {"train", "test", "wf", "train_factor"}
    panel = result["train_factor"]
    assert isinstance(panel, pd.Series)
    assert panel.index.names == ["datetime", "symbol"]
    assert len(panel.dropna()) > 0


def test_low_corr_pair_measured_below_threshold(service):
    # 直接对真实 train 面板实测：Provider 合成数据下二者 = -0.0038（成交量与价格独立生成）
    raw_map = load_raw_ohlcv(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "1h", "spot", None, None, Provider())
    a = service.analyze_code_panel(CODE_MOM, raw_map, interval="1h", test_ratio=0)
    b = service.analyze_code_panel(CODE_VOL_MOM, raw_map, interval="1h", test_ratio=0)
    corr = miner._factor_corr(a["train_factor"], b["train_factor"])
    assert corr is not None
    assert abs(corr) < 0.9


def test_dedup_high_corr_pair_marks_lower_one_redundant(service):
    result = run_llm_mining(
        _params(n_candidates=2, dedup_corr=0.9),
        backend=FakeBackend([CODE_MOM, CODE_MOM_SCALED]),
        provider=Provider(),
        service=service,
    )
    succ = [c for c in result["candidates"] if c["status"] == "success"]
    assert len(succ) == 2
    redundant = [r for r in succ if r["redundant"]]
    kept = [r for r in succ if not r["redundant"]]
    assert len(redundant) == 1
    assert len(kept) == 1
    flag = redundant[0]
    assert flag["redundant_with"] == kept[0]["code_hash"]
    assert flag["redundant_corr"] is not None
    assert abs(flag["redundant_corr"]) > 0.99
    # best 只留非冗余
    assert len(result["best"]) == 1
    assert result["best"][0]["code_hash"] == kept[0]["code_hash"]
    assert result["stats"]["redundant"] == 1


def test_dedup_low_corr_pair_both_kept(service):
    result = run_llm_mining(
        _params(n_candidates=2, dedup_corr=0.9),
        backend=FakeBackend([CODE_MOM, CODE_VOL_MOM]),
        provider=Provider(),
        service=service,
    )
    succ = [c for c in result["candidates"] if c["status"] == "success"]
    assert len(succ) == 2
    assert all(not r["redundant"] for r in succ)
    assert all(r["redundant_with"] is None and r["redundant_corr"] is None for r in succ)
    assert len(result["best"]) == 2
    assert result["stats"]["redundant"] == 0


def test_dedup_disabled_when_threshold_zero(service):
    result = run_llm_mining(
        _params(n_candidates=2, dedup_corr=0.0),
        backend=FakeBackend([CODE_MOM, CODE_MOM_SCALED]),
        provider=Provider(),
        service=service,
    )
    succ = [c for c in result["candidates"] if c["status"] == "success"]
    assert len(succ) == 2
    assert all(not r["redundant"] for r in succ)
    assert len(result["best"]) == 2
    assert result["stats"]["redundant"] == 0


def test_best_excludes_redundant_and_respects_top_k(service):
    # 三个成功候选：MOM 与其单调变换互为冗余，成交量动量独立 -> 2 个非冗余
    result = run_llm_mining(
        _params(n_candidates=3, top_k=1, dedup_corr=0.9),
        backend=FakeBackend([CODE_MOM, CODE_MOM_SCALED, CODE_VOL_MOM]),
        provider=Provider(),
        service=service,
    )
    assert len(result["best"]) == 1
    assert not result["best"][0]["redundant"]
    assert result["stats"]["redundant"] == 1
    # 放开 top_k 后两个非冗余都进 best
    result2 = run_llm_mining(
        _params(n_candidates=3, top_k=5, dedup_corr=0.9),
        backend=FakeBackend([CODE_MOM, CODE_MOM_SCALED, CODE_VOL_MOM]),
        provider=Provider(),
        service=service,
    )
    assert len(result2["best"]) == 2
    assert all(not r["redundant"] for r in result2["best"])


def test_correlation_dedup_keeps_higher_fitness_when_input_shuffled():
    # 乱序输入（低 fitness 在前）：去重后仍保留高 fitness 行，低者指向高者 hash
    base = np.random.default_rng(2).normal(size=40)
    f_high = _mi_panel({"BTCUSDT": base, "ETHUSDT": base * 2.0})
    f_low = _mi_panel({"BTCUSDT": base * 1000.0 + 3.0, "ETHUSDT": base * 2000.0 + 3.0})

    def row(hash_, fitness, factor):
        return {
            "status": "success",
            "code_hash": hash_,
            "metrics": {"fitness": fitness},
            "_factor": factor,
            "redundant": False,
            "redundant_with": None,
            "redundant_corr": None,
        }

    # 非 success 行不带冗余字段，函数不得触碰
    failed = {"status": "runtime_error", "code_hash": "", "metrics": None}
    rows = [row("low", 1.0, f_low), failed, row("high", 10.0, f_high)]
    correlation_dedup(rows, 0.9)
    by_hash = {r["code_hash"]: r for r in rows if r["status"] == "success"}
    assert by_hash["high"]["redundant"] is False
    assert by_hash["low"]["redundant"] is True
    assert by_hash["low"]["redundant_with"] == "high"
    assert abs(by_hash["low"]["redundant_corr"]) > 0.99
    assert "redundant" not in failed


def test_dedup_skipped_when_corr_uncomputable(service, monkeypatch):
    # _factor_corr 全部返回 None（配对不足）-> 高相关对也不去重
    monkeypatch.setattr(miner, "_factor_corr", lambda *a, **k: None)
    result = run_llm_mining(
        _params(n_candidates=2, dedup_corr=0.9),
        backend=FakeBackend([CODE_MOM, CODE_MOM_SCALED]),
        provider=Provider(),
        service=service,
    )
    succ = [c for c in result["candidates"] if c["status"] == "success"]
    assert all(not r["redundant"] for r in succ)
    assert len(result["best"]) == 2
    assert result["stats"]["redundant"] == 0


def test_result_rows_strip_internal_factor_and_are_json_serializable(service):
    result = run_llm_mining(
        _params(n_candidates=2, dedup_corr=0.9),
        backend=FakeBackend([CODE_MOM, CODE_MOM_SCALED]),
        provider=Provider(),
        service=service,
    )
    for r in result["candidates"] + result["best"]:
        assert "_factor" not in r
        assert "train_factor" not in r
    # 无 Series 残留：不用 default=str 也必须能直接 JSON 序列化
    json.dumps(result)


# ---------------------------------------------------------------------------
# 合成因子（IC 加权 zscore）：挖掘内自动合成
# ---------------------------------------------------------------------------


def test_mine_composes_two_low_corr_best(service):
    result = run_llm_mining(
        _params(n_candidates=2, test_ratio=0.3),
        backend=FakeBackend([CODE_MOM, CODE_VOL_MOM]),
        provider=Provider(),
        service=service,
    )
    comp = result["composite"]
    assert comp is not None
    assert "error" not in comp
    assert result["stats"]["composed"] is True
    assert comp["n"] == 2
    assert len(comp["constituents"]) == 2

    # 权重：绝对值和≈1（带符号归一），且与各成分 train IC 同号
    ic_by_hash = {c["code_hash"]: c["metrics"]["ic_mean"] for c in result["candidates"]}
    weights = [c["weight"] for c in comp["constituents"]]
    assert sum(abs(w) for w in weights) == pytest.approx(1.0, abs=1e-9)
    for c in comp["constituents"]:
        assert c["weight"] * ic_by_hash[c["code_hash"]] > 0
        assert c["ts_stats"]  # 每成分带冻结的逐品种时序统计
        json.dumps(c["ts_stats"])

    # train/OOS 指标口径与候选行一致
    assert comp["metrics"]["ic_mean"] is not None
    assert comp["metrics_oos"] is not None
    assert comp["metrics_oos"]["ic_mean"] is not None
    assert comp["oos_flag"] in {"ok", "weak", "sign_flip"}
    tw = comp["train_window"]
    assert tw["start"] < tw["end"]
    assert tw["interval"] == "1h" and tw["candle_type"] == "spot"
    assert "folds" not in comp  # 单次切分路径不带 folds
    # 整体必须是 JSON 原生类型（无 Series/numpy 残留）
    json.dumps(result)


def test_mine_composition_wf_emits_folds(service):
    result = run_llm_mining(
        _params(n_candidates=2, test_ratio=0.3, wf_folds=3),
        backend=FakeBackend([CODE_MOM, CODE_VOL_MOM]),
        provider=Provider(),
        service=service,
    )
    comp = result["composite"]
    assert comp is not None and "error" not in comp
    assert len(comp["folds"]) == 3
    assert comp["metrics_oos"]["n_folds"] == 3
    json.dumps(result)


def test_mine_compose_disabled_returns_none(service):
    result = run_llm_mining(
        _params(n_candidates=2, compose=False),
        backend=FakeBackend([CODE_MOM, CODE_VOL_MOM]),
        provider=Provider(),
        service=service,
    )
    assert result["composite"] is None
    assert result["stats"]["composed"] is False


def test_mine_composite_none_when_best_less_than_two(service):
    result = run_llm_mining(
        _params(n_candidates=1, test_ratio=0.3),
        backend=FakeBackend([CODE_MOM]),
        provider=Provider(),
        service=service,
    )
    assert result["composite"] is None
    assert result["stats"]["composed"] is False


def test_mine_composite_failure_does_not_block_mining(service, monkeypatch):
    # analyze_composite 抛错 → composite={"error":...}，候选结果照常返回
    def boom(*a, **k):
        raise RuntimeError("compose boom")

    monkeypatch.setattr(service, "analyze_composite", boom)
    result = run_llm_mining(
        _params(n_candidates=2, test_ratio=0.3),
        backend=FakeBackend([CODE_MOM, CODE_VOL_MOM]),
        provider=Provider(),
        service=service,
    )
    comp = result["composite"]
    assert comp is not None
    assert "error" in comp and "boom" in comp["error"]
    assert result["stats"]["composed"] is False
    assert len(result["best"]) == 2
    json.dumps(result)


def test_non_success_rows_have_redundant_defaults(service):
    result = run_llm_mining(
        _params(n_candidates=1),
        backend=FakeBackend(["import os\nfactor = 1"]),
        provider=Provider(),
        service=service,
    )
    row = result["candidates"][0]
    assert row["status"] == "security_error"
    assert row["redundant"] is False
    assert row["redundant_with"] is None
    assert row["redundant_corr"] is None


def test_progress_monotonic_and_emits_candidate_events(service):
    events = []
    progress = []
    run_llm_mining(
        _params(n_candidates=3, n_rounds=1),
        backend=FakeBackend(
            [
                '```python\nfactor = df["close"].pct_change(5)\n```',
                "import os\nfactor = 1",  # AST 静态安全拒绝，仍占一个评估段事件
                'factor = df["volume"] / df["volume"].rolling(20).mean()',
            ]
        ),
        provider=Provider(),
        service=service,
        progress=lambda p, s, m: progress.append(p),
        on_event=lambda level, stage, p, msg: events.append((level, stage, p, msg)),
    )
    # progress 回调仍被驱动：首尾递增（回归 test_progress_callback_called 口径）
    assert progress[0] < progress[-1] == 100.0
    assert progress == sorted(progress)  # 单调不减
    stages = [e[1] for e in events]
    assert stages[0] == "data_load"
    # 每个并发 LLM 返回一条 generating 事件（轮开始/轮末的 generating 不计入）
    gen_done = [e for e in events if e[1] == "generating" and "LLM 返回" in e[3]]
    assert len(gen_done) == 3
    assert "evaluating" in stages
    assert "dedup" in stages and "completed" in stages
    # 带 p 的事件，其 p 单调不减
    ps = [e[2] for e in events if e[2] is not None]
    assert ps == sorted(ps)


def test_on_event_none_keeps_default_behavior(service):
    # 不传 on_event 也能正常跑完（回归既有用例的默认路径）
    result = run_llm_mining(
        _params(n_candidates=1),
        backend=FakeBackend(['factor = df["close"].pct_change(3)']),
        provider=Provider(),
        service=service,
    )
    assert result["stats"]["generated"] == 1
