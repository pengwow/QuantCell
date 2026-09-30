# LLM 挖掘闭环测试：用 Fake backend 回放预置代码，覆盖成功/静态失败/运行失败/反思/去重
import pytest

from factor.code_store import CodeFactorStore
from factor.llm_miner import LLMMineParams, run_llm_mining
from factor.sandbox import FactorSandbox
from factor.service import FactorService


class FakeBackend:
    """按调用顺序回放 content；记录消息供断言反思上下文。"""

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = []

    async def chat_async(self, messages):
        self.calls.append(messages)
        content = self._contents[(len(self.calls) - 1) % len(self._contents)]
        return {
            "content": content,
            "finish_reason": "Stop",
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
