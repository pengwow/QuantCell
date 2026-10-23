"""LLM 决策可回放（录制/回放 provider）单元测试。

覆盖：录制落盘、回放命中、miss 必须抛错、策略层不得降级、
回测入口缺记录 4xx、以及 llm_signal 端到端两次运行结果一致。
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

from backtest.backtest_loop import BacktestLoop
from backtest.routes import run_backtest
from backtest.schemas import BacktestConfig, BacktestRunRequest, StrategyConfig
from strategy.base import StrategyConfig as RuntimeStrategyConfig
from strategy.base import StrategyContext
from strategy.llm_replay import (
    RecordingProvider,
    ReplayMissError,
    ReplayProvider,
    request_fingerprint,
    wrap_llm_provider,
)
from strategy.templates.llm_signal import LLMSignalStrategy


def _bar(price: float) -> dict:
    return {
        "open": price,
        "high": price * 1.001,
        "low": price * 0.999,
        "close": price,
        "volume": 100.0,
    }


def _kline(n: int = 60) -> pd.DataFrame:
    """正弦震荡 K 线：每根 bar 的 prompt 都不同，fingerprint 应逐 bar 唯一。"""
    dates = pd.date_range("2024-07-01", periods=n, freq="1h")
    closes = [100.0 + 10.0 * math.sin(i / 5.0) for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=dates,
    )


def _mock_llm(_prompt: str) -> str:
    """固定响应，保证两次运行唯一变量只有 provider 的录制/回放。"""
    return '{"action":"Buy","confidence":0.8,"reasoning":"mock"}'


def test_recording_writes_fingerprint_and_response(tmp_path: Path) -> None:
    """录制 provider 把 (fingerprint, response) 追加写入 JSONL。"""
    path = tmp_path / "record.jsonl"
    provider = RecordingProvider(lambda prompt: f"echo:{prompt}", path)

    assert provider("hello") == "echo:hello"
    assert provider("hello") == "echo:hello"  # 同一 prompt 只落一行
    assert provider("world") == "echo:world"

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0] == {
        "fingerprint": hashlib.sha256(b"hello").hexdigest(),
        "response": "echo:hello",
    }
    assert lines[1]["fingerprint"] == request_fingerprint("world")
    assert lines[1]["response"] == "echo:world"


def test_replay_hits_recorded_response(tmp_path: Path) -> None:
    """回放 provider 命中原样返回录制的响应。"""
    path = tmp_path / "record.jsonl"
    RecordingProvider(lambda _prompt: "recorded-answer", path)("prompt-1")

    replay = ReplayProvider(path)
    assert replay("prompt-1") == "recorded-answer"
    assert replay.hits == 1


def test_replay_miss_raises(tmp_path: Path) -> None:
    """未命中的请求必须抛 ReplayMissError，不能返回空串。"""
    path = tmp_path / "record.jsonl"
    RecordingProvider(lambda _prompt: "recorded-answer", path)("prompt-1")
    replay = ReplayProvider(path)

    with pytest.raises(ReplayMissError, match="未命中"):
        replay("prompt-2")


def test_replay_does_not_fallback_to_heuristic(tmp_path: Path) -> None:
    """策略层不得把回放 miss 吞成 Hold 或 heuristic 信号。"""
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")

    strategy = LLMSignalStrategy(
        RuntimeStrategyConfig(
            name="llm_signal",
            params={"mode": "llm", "fast": 3, "slow": 5, "llm_provider": ReplayProvider(empty)},
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT")
    strategy.on_start(ctx)

    with pytest.raises(ReplayMissError):
        strategy.on_bar(_bar(100.0), ctx)


def test_llm_backtest_without_replay_file_is_rejected_4xx(tmp_path: Path, monkeypatch) -> None:
    """回测入口缺少 replay 记录时返回 400，而不是带病开跑。"""
    # 隔离默认录制目录，避免本机残留文件让用例误判
    monkeypatch.setenv("QUANTCELL_LLM_REPLAY_DIR", str(tmp_path / "replay_dir"))
    missing = tmp_path / "not_exists.jsonl"
    request = BacktestRunRequest(
        strategy_config=StrategyConfig(
            strategy_name="llm_signal",
            params={"mode": "llm", "llm_replay_path": str(missing)},
        ),
        backtest_config=BacktestConfig(
            symbols=["BTCUSDT"],
            start_time="2024-07-01 00:00:00",
            end_time="2024-07-02 00:00:00",
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        run_backtest(request)

    assert exc_info.value.status_code == 400
    assert "replay" in str(exc_info.value.detail)
    assert "heuristic" in str(exc_info.value.detail)


def test_llm_signal_backtest_replay_is_reproducible(tmp_path: Path, monkeypatch) -> None:
    """端到端：paper 录制 → 回测回放，逐 bar fingerprint 全命中且结果一致。"""
    monkeypatch.setenv("QUANTCELL_LLM_REPLAY_DIR", str(tmp_path / "replay_dir"))
    path = tmp_path / "llm_signal.jsonl"
    params = {
        "mode": "llm",
        "signal_interval": 1,
        "llm_provider": _mock_llm,
        "llm_replay_path": str(path),
    }
    data = _kline()

    # ① paper 运行：wrap_llm_provider 把真实 provider 包成 RecordingProvider
    rec_params = wrap_llm_provider("llm_signal", dict(params), "paper")
    assert isinstance(rec_params["llm_provider"], RecordingProvider)
    rec_strategy = LLMSignalStrategy(RuntimeStrategyConfig(name="llm_signal", params=rec_params))
    first = BacktestLoop(initial_cash=100_000.0).run(rec_strategy, data, symbol="BTCUSDT")

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == len(data), "signal_interval=1 时每根 bar 都应有一条 LLM 记录"
    assert len({r["fingerprint"] for r in records}) == len(records), "逐 bar prompt 不同，fingerprint 应唯一"

    # ② 回测运行：provider 被换成 ReplayProvider，不触网
    replay_params = wrap_llm_provider("llm_signal", dict(params), "backtest")
    replay_provider = replay_params["llm_provider"]
    assert isinstance(replay_provider, ReplayProvider)
    replay_strategy = LLMSignalStrategy(RuntimeStrategyConfig(name="llm_signal", params=replay_params))
    second = BacktestLoop(initial_cash=100_000.0).run(replay_strategy, data, symbol="BTCUSDT")

    assert replay_provider.hits == len(data), "逐 bar fingerprint 必须全部命中"
    assert second.total_pnl == first.total_pnl
    assert second.final_nav == first.final_nav
    assert second.fills == first.fills
    assert len(second.trade_records) == len(first.trade_records)
