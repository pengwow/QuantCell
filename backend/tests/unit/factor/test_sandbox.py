# LLM 因子代码沙箱测试：静态策略 / 子进程执行 / 资源限额 / 输出契约
import time

import numpy as np
import pandas as pd
import pytest

from factor.sandbox import (
    FactorSandbox,
    SandboxError,
    SandboxOutputError,
    SandboxResourceError,
    SandboxSecurityError,
    SandboxTimeoutError,
    synthetic_raw_map,
)


@pytest.fixture(scope="module")
def sandbox():
    # 子进程启动有固定成本，整个模块复用一个实例
    return FactorSandbox()


@pytest.fixture(scope="module")
def frames():
    return synthetic_raw_map(n=200, symbols=["BTCUSDT", "ETHUSDT"])


class TestStaticPolicy:
    def test_valid_momentum_code_passes(self, sandbox):
        sandbox.check_static('factor = df["close"].pct_change(5)')

    def test_multi_line_code_with_helper_vars_passes(self, sandbox):
        code = (
            'ma = df["close"].rolling(20).mean()\n'
            'std = df["close"].rolling(20).std()\n'
            "factor = (df["
            '"close"] - ma) / std.replace(0.0, np.nan)'
        )
        sandbox.check_static(code)

    @pytest.mark.parametrize(
        "code",
        [
            "import os",
            "from os import path",
            "__import__('os').system('id')",
            "factor = df.__class__",
            "factor = df['close'].__dict__",
            "factor = open('/etc/passwd').read()",
            "eval('1+1')",
            "df = None",
            "_secret = 1",
            "factor = [x for x in df['close']]",
            "lambda: 1",
            # while 不在 AST 白名单：死循环先由静态策略拦截，
            # 真正的 CPU/超时资源限额验证见 TestExecution.test_infinite_loop_hits_resource_limit
            "while True:\n    pass",
        ],
    )
    def test_forbidden_syntax_blocked(self, sandbox, code):
        with pytest.raises(SandboxSecurityError):
            sandbox.check_static(code)

    def test_must_assign_factor_variable(self, sandbox):
        with pytest.raises(SandboxOutputError):
            sandbox.check_static('x = df["close"] + 1')

    def test_dynamic_kwargs_blocked(self, sandbox):
        with pytest.raises(SandboxSecurityError):
            sandbox.check_static('factor = df["close"].rolling(20).mean(**{"w": 1})')


class TestExecution:
    def test_valid_code_returns_series_per_symbol(self, sandbox, frames):
        series = sandbox.run('factor = df["close"].pct_change(5)', frames)
        assert set(series) == {"BTCUSDT", "ETHUSDT"}
        for symbol, s in series.items():
            assert isinstance(s, pd.Series)
            assert len(s) == len(frames[symbol])
            assert s.index.equals(frames[symbol].index)
            assert s.iloc[5:].notna().all()

    def test_derived_vwap_and_amount_columns_available(self, sandbox, frames):
        # 列契约与表达式引擎 _column_env 对齐：vwap/amount 由沙箱统一派生，
        # 防止挖掘 prompt 承诺的列在真实 parquet（只有 7 个原始列）上 KeyError
        series = sandbox.run(
            'factor = (df["close"] - df["vwap"]) + df["amount"] * 0.0',
            frames,
        )
        assert series["BTCUSDT"].notna().any()

    def test_run_does_not_mutate_caller_frames(self, sandbox, frames):
        raw_cols = set(frames["BTCUSDT"].columns)
        sandbox.run('factor = df["close"].pct_change(1)', frames)
        assert set(frames["BTCUSDT"].columns) == raw_cols

    def test_numpy_helpers_allowed(self, sandbox, frames):
        # np.where 输出裸 ndarray，必须按输出契约显式包成对齐 df.index 的 Series
        # （runner 与参考实现 FactorMiner 均不接受裸 ndarray）
        series = sandbox.run(
            'factor = pd.Series(np.where(df["close"] > df["open"], 1.0, -1.0), index=df.index)',
            frames,
        )
        assert set(series["BTCUSDT"].dropna().unique()) == {-1.0, 1.0}

    def test_wrong_length_rejected(self, sandbox, frames):
        with pytest.raises(SandboxOutputError):
            sandbox.run('factor = df["close"].dropna().head(3)', frames)

    def test_non_numeric_rejected(self, sandbox, frames):
        with pytest.raises(SandboxOutputError):
            sandbox.run('factor = df["close"].astype(str)', frames)

    def test_all_nan_rejected(self, sandbox, frames):
        with pytest.raises(SandboxOutputError):
            sandbox.run("factor = pd.Series(np.nan, index=df.index)", frames)

    def test_inf_rejected(self, sandbox, frames):
        with pytest.raises(SandboxOutputError):
            sandbox.run(
                'factor = df["close"] / df["close"].where(df["close"] > 1e12)',
                frames,
            )

    def test_runtime_error_is_sandbox_runtime(self, sandbox, frames):
        from factor.sandbox import SandboxRuntimeError

        with pytest.raises(SandboxRuntimeError):
            sandbox.run('factor = df["not_a_column"] + 1', frames)

    def test_infinite_loop_hits_resource_limit(self, sandbox, frames):
        # 绕过静态策略（runner 不做 AST 检查），直接验证 rlimit CPU / wall-clock 资源限额
        t0 = time.monotonic()
        payload = {
            "code": "while True:\n    pass",
            "frames": {"BTCUSDT": frames["BTCUSDT"]},
            "limits": {
                "cpu_seconds": sandbox.limits.cpu_seconds,
                "memory_mb": sandbox.limits.memory_mb,
            },
        }
        with pytest.raises((SandboxTimeoutError, SandboxResourceError)):
            sandbox._spawn(payload)
        # wall-clock 10s 上限；CPU 限额通常先触发（3s），两种都接受
        assert time.monotonic() - t0 < 12

    def test_memory_bomb_blocked(self, sandbox, frames):
        # np.ones(60_000_000) ≈ 480MB。macOS 不强制 RLIMIT_AS 且 calloc 惰性零页
        # 不占物理内存（实测裸 np.ones(200_000_000) 都不会被拦截），因此乘以 1.0
        # 强制触碰全部物理页，由 runner 的峰值 RSS 兜底拒绝；输出本身合法，
        # 证明这是纯粹的资源限额拦截而非输出契约拦截。
        code = 'big = np.ones(60_000_000) * 1.0\nfactor = df["close"]'
        with pytest.raises(SandboxResourceError):
            sandbox.run(code, {"BTCUSDT": frames["BTCUSDT"]})

    def test_network_call_blocked_by_policy(self, sandbox, frames):
        # socket 不是合法节点调用；import 已在静态层封死
        with pytest.raises(SandboxSecurityError):
            sandbox.check_static(
                "import socket\ns = socket.socket()\ns.connect(('127.0.0.1', 80))\nfactor = df[\"close\"]"
            )


class TestValidateSynthetic:
    def test_validate_ok(self, sandbox):
        sandbox.validate('factor = df["close"].rolling(10).mean() / df["close"] - 1')

    def test_validate_bad_code_raises(self, sandbox):
        with pytest.raises(SandboxError):
            sandbox.validate("factor = 1/0")
