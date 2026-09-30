"""LLM 因子代码安全沙箱 —— AST 白名单 + 独立子进程 + 资源限额 + 输出契约。

三层防线见本模块计划文档「威胁模型」节。父进程只做静态校验与子进程编排，
绝不在本进程 exec 不可信代码。

ponytail: 研究级防护而非多租户安全边界（无内核级网络/FS 隔离），升级路径
sandbox-exec/bubblewrap。子进程按文件路径启动 sandbox_runner.py，不经过
factor/__init__ 的重依赖链。
"""

from __future__ import annotations

import ast
import pickle
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

_RUNNER_PATH = Path(__file__).with_name("sandbox_runner.py")
_MAGIC = b"FCSB01\n"
_HEADER_LEN = 8


class SandboxError(Exception):
    """沙箱错误基类。"""


class SandboxSecurityError(SandboxError):
    """代码违反静态安全策略。"""


class SandboxOutputError(SandboxError):
    """代码未给 factor 赋值，或输出违反 Series 契约。"""


class SandboxTimeoutError(SandboxError):
    """执行超过 wall-clock 预算。"""


class SandboxResourceError(SandboxError):
    """触发 CPU/内存限额（含子进程被 SIGXCPU/SIGKILL 终止）。"""


class SandboxRuntimeError(SandboxError):
    """代码在沙箱内运行失败或 worker 崩溃。"""


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: float = 10.0
    cpu_seconds: int = 3
    # Task1（macOS arm64 + Python 3.14）实测校准，定稿 400MB：
    # - 正常因子子进程峰值物理内存约 170MiB（含 numpy/pandas 导入与计算），
    #   400MB 下 test_valid_code_returns_series_per_symbol 等全部正常用例通过，余量约 230MB；
    # - 480MB 物理内存炸弹（np.ones(60_000_000)*1.0 强制触页）被稳定拒绝。
    # - macOS 内核基本不强制 RLIMIT_AS：裸 np.ones(200_000_000)（约 1.6GB，
    #   calloc 惰性零页）也不报错，因此 macOS 的内存防线实际由 runner 的
    #   峰值 RSS（ru_maxrss）事后兜底，RLIMIT_AS 只在 Linux 上是硬限制；
    # - 若将来 Linux 部署出现合法因子被 MemoryError 误杀（RLIMIT_AS 计虚拟
    #   地址空间，口径比 RSS 紧），按本注释实测口径上调到 512。
    memory_mb: int = 400


_SAFE_BUILTINS = {
    "abs",
    "min",
    "max",
    "len",
    "range",
    "list",
    "dict",
    "float",
    "int",
    "bool",
    "str",
    "sum",
    "sorted",
    "enumerate",
    "zip",
    "round",
    "any",
    "all",
}

# 向量化因子常用的 pandas/numpy 属性白名单（属性必须真实存在才能运行）
_SAFE_ATTRIBUTES = {
    # pandas Series/DataFrame 变换
    "abs",
    "add",
    "sub",
    "mul",
    "div",
    "pow",
    "radd",
    "rsub",
    "rmul",
    "rdiv",
    "clip",
    "corr",
    "cummax",
    "cummin",
    "cumprod",
    "cumsum",
    "diff",
    "divide",
    "dropna",
    "ewm",
    "expanding",
    "fillna",
    "index",
    "isna",
    "notna",
    "isnull",
    "notnull",
    "log",
    "map",
    "mask",
    "max",
    "mean",
    "median",
    "min",
    "multiply",
    "pct_change",
    "quantile",
    "rank",
    "repeat",
    "replace",
    "rolling",
    "shift",
    "sign",
    "std",
    "subtract",
    "sum",
    "var",
    "where",
    "select",
    "values",
    "name",
    "dtype",
    "shape",
    "iloc",
    "loc",
    "reset_index",
    "set_index",
    "groupby",
    "unstack",
    "stack",
    "rename",
    "copy",
    "astype",
    "to_numpy",
    "between",
    "gt",
    "lt",
    "ge",
    "le",
    "eq",
    "ne",
    "add_prefix",
    "head",
    # numpy 入口（与上面 pandas 组同名的方法不再重复列出）
    "Series",
    "DataFrame",
    "array",
    "exp",
    "log1p",
    "log2",
    "sqrt",
    "maximum",
    "minimum",
    "nan",
    "NaN",
    "inf",
    "ones",
    "zeros",
    "arange",
    "linspace",
    "power",
    "square",
    "floor",
    "ceil",
    "pi",
    "e",
}

_ALLOWED_NODES = (
    ast.Module,
    ast.Assign,
    ast.Expr,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.Subscript,
    ast.Slice,
    ast.Tuple,
    ast.List,
    ast.Dict,
    ast.Call,
    ast.Attribute,
    ast.keyword,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Invert,
    ast.And,
    ast.Or,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


class FactorCodePolicy(ast.NodeVisitor):
    """因子代码 AST 白名单：fail-closed，任何未列出的节点直接拒绝。"""

    def validate(self, code: str) -> ast.Module:
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            raise SandboxSecurityError(f"代码语法错误: {exc.msg}（第 {exc.lineno} 行）") from exc
        self.assigned: set[str] = set()
        self.factor_assigned = False
        self.visit(tree)
        if not self.factor_assigned:
            raise SandboxOutputError("代码必须把最终因子赋值给变量 factor")
        return tree

    def generic_visit(self, node: ast.AST) -> None:
        if not isinstance(node, _ALLOWED_NODES):
            raise SandboxSecurityError(f"不允许的语法: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if not isinstance(target, ast.Name):
                raise SandboxSecurityError("只允许给普通局部变量赋值")
            if target.id in {"df", "np", "pd"} or target.id in _SAFE_BUILTINS:
                raise SandboxSecurityError(f"不允许重写受保护名称 '{target.id}'")
            if target.id.startswith("_"):
                raise SandboxSecurityError("不允许下划线/dunder 变量名")
            self.assigned.add(target.id)
            if target.id == "factor":
                self.factor_assigned = True
        self.visit(node.value)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("_"):
            raise SandboxSecurityError("不允许下划线/dunder 名称")
        if isinstance(node.ctx, ast.Load):
            allowed = {"df", "np", "pd"} | _SAFE_BUILTINS | self.assigned
            if node.id not in allowed:
                raise SandboxSecurityError(f"不允许使用名称 '{node.id}'（禁止 import/内置函数/文件访问）")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_") or node.attr not in _SAFE_ATTRIBUTES:
            raise SandboxSecurityError(f"不允许的属性/方法 '{node.attr}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id not in _SAFE_BUILTINS:
                raise SandboxSecurityError(f"不允许直接调用 '{node.func.id}'")
        elif not isinstance(node.func, ast.Attribute):
            raise SandboxSecurityError("只允许白名单内置函数或属性调用")
        self.generic_visit(node)
        for kw in node.keywords:
            if kw.arg is None or kw.arg.startswith("_"):
                raise SandboxSecurityError("不允许 **kwargs 动态参数或下划线参数")


def with_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """补齐因子统一列契约：vwap=成交额/成交量、amount=成交量*收盘价。

    表达式引擎 factor.engine._column_env 同源派生这两列；代码因子沙箱必须
    提供相同列集合，否则挖掘 prompt 承诺的 df["vwap"]/df["amount"] 在运行时
    直接 KeyError。copy 后再加列，避免修改 parquet provider 可能被缓存共享的
    原始 DataFrame（engine 面板路径已有同样的 copy 约定）。
    """
    out = df.copy()
    # volume 为 0 的 bar 无法算成交均价，置 NaN 而不是 inf（输出契约禁止 inf）
    out["vwap"] = out["quote_volume"] / out["volume"].replace(0, np.nan)
    out["amount"] = out["volume"] * out["close"]
    return out


def synthetic_raw_map(n: int = 200, symbols: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """生成确定性合成 K 线（含沙箱可用的全部列），供代码验证与测试使用。"""
    symbols = symbols or ["BTCUSDT"]
    frames = {}
    for k, symbol in enumerate(symbols):
        rng = np.random.default_rng(42 + k)
        close = 100.0 + np.cumsum(rng.normal(0, 1, n))
        volume = rng.uniform(100, 1000, n)
        frames[symbol] = with_derived_columns(
            pd.DataFrame(
                {
                    "open": close + rng.normal(0, 0.2, n),
                    "high": close + np.abs(rng.normal(0, 0.5, n)),
                    "low": close - np.abs(rng.normal(0, 0.5, n)),
                    "close": close,
                    "volume": volume,
                    "quote_volume": close * volume,
                }
            )
        )
    return frames


class FactorSandbox:
    """静态校验 → 子进程执行 → 结果分类的父进程门面（无状态，可共享单例）。"""

    def __init__(
        self,
        timeout_seconds: float = SandboxLimits.timeout_seconds,
        cpu_seconds: int = SandboxLimits.cpu_seconds,
        memory_mb: int = SandboxLimits.memory_mb,
    ) -> None:
        self.limits = SandboxLimits(
            timeout_seconds=float(timeout_seconds),
            cpu_seconds=int(cpu_seconds),
            memory_mb=int(memory_mb),
        )

    def check_static(self, code: str) -> ast.Module:
        return FactorCodePolicy().validate(code)

    def validate(self, code: str) -> None:
        """静态策略 + 合成数据真实执行，供 /code/validate 与入库前校验。"""
        self.check_static(code)
        self.run(code, synthetic_raw_map(n=120))

    def run(self, code: str, frames: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        """在一个子进程内逐品种执行代码，返回 {symbol: Series}。"""
        self.check_static(code)
        if not frames:
            raise SandboxRuntimeError("没有可用的行情数据")
        # 统一补 vwap/amount 派生列（copy 在函数内完成，不改调用方 raw_map）
        frames = {symbol: with_derived_columns(df) for symbol, df in frames.items()}
        payload = {
            "code": code,
            "frames": frames,
            "limits": {
                "cpu_seconds": self.limits.cpu_seconds,
                "memory_mb": self.limits.memory_mb,
            },
        }
        return self._spawn(payload)

    def _spawn(self, payload: dict[str, Any]) -> dict[str, pd.Series]:
        blob = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        # 只持有本 Popen 句柄；超时时只 kill 这一个子进程（禁止全局杀 python）
        proc = subprocess.Popen(
            [sys.executable, str(_RUNNER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        try:
            # 与 runner 协议对齐：stdin 必须先发 8 字节大端长度帧头再发 pickle
            out, err = proc.communicate(
                struct.pack(">Q", len(blob)) + blob,
                timeout=self.limits.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            _, err = proc.communicate()
            raise SandboxTimeoutError(f"因子代码执行超过 {self.limits.timeout_seconds:.0f}s 上限") from exc

        if proc.returncode != 0:
            raise self._classify_signal_death(proc.returncode, err)

        if not out.startswith(_MAGIC):
            tail = err[-400:].decode(errors="ignore") if err else ""
            raise SandboxRuntimeError(f"沙箱协议错误（输出帧头缺失）。stderr: {tail}")

        (body_len,) = struct.unpack(">Q", out[len(_MAGIC) : len(_MAGIC) + _HEADER_LEN])
        result = pickle.loads(out[len(_MAGIC) + _HEADER_LEN : len(_MAGIC) + _HEADER_LEN + body_len])

        if result["status"] == "success":
            return result["series"]

        error_type = result.get("error_type", "Exception")
        message = result.get("message", "未知错误")
        self._raise_typed(error_type, message)

    @staticmethod
    def _classify_signal_death(returncode: int, err: bytes) -> SandboxError:
        tail = err[-400:].decode(errors="ignore") if err else ""
        # SIGXCPU=24 被 rlimit CPU 杀；SIGKILL=9 多为内存超限被系统杀
        if returncode == -24:
            return SandboxResourceError(f"因子代码超过 CPU 时间限额。{tail}")
        if returncode == -9:
            return SandboxResourceError(f"因子代码内存超限被系统终止。{tail}")
        return SandboxRuntimeError(f"沙箱进程崩溃(exit={returncode})。{tail}")

    @staticmethod
    def _raise_typed(error_type: str, message: str) -> None:
        if error_type in {"TypeError", "ValueError"} and (
            "factor" in message or "Series" in message or "inf" in message
        ):
            raise SandboxOutputError(message)
        if error_type == "MemoryError":
            raise SandboxResourceError(message)
        raise SandboxRuntimeError(f"{error_type}: {message}")
