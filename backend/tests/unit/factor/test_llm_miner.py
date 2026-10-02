# LLM 挖掘闭环测试：用 Fake backend 回放预置代码，覆盖成功/静态失败/运行失败/反思/去重
import pytest

from factor.code_store import CodeFactorStore
from factor.llm_miner import LLMMineParams, oos_flag, run_llm_mining
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
