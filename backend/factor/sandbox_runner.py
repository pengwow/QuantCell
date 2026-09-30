#!/usr/bin/env python3
"""LLM 因子沙箱子进程入口。

本文件按「文件路径」被子进程启动（python factor/sandbox_runner.py），
严禁 import factor 包内任何模块——否则 spawn 会执行 factor/__init__.py
的 FastAPI/SQLAlchemy 重依赖链，每个候选因子白白损失数秒启动成本。

协议（二进制帧，噪声只允许进 stderr）：
  stdin:  8 字节大端长度 + pickle payload
  stdout: MAGIC + 8 字节大端长度 + pickle result
  payload = {"code": str, "frames": {symbol: DataFrame},
             "limits": {"cpu_seconds": int, "memory_mb": int}}
  result  = {"status": "success", "series": {symbol: Series}}
          | {"status": "error", "error_type": str, "message": str}
解释器级崩溃（SIGXCPU/SIGKILL/段错误）由父进程按退出码与 stderr 处理。
"""

from __future__ import annotations

import pickle
import struct
import sys
import traceback

MAGIC = b"FCSB01\n"
_HEADER_LEN = 8

# 与 sandbox.py 保持同源的最小白名单（子进程不信任父进程传入的环境）
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


def _apply_limits(limits: dict) -> None:
    """在 import numpy/pandas 之前设置资源限额，让大数据分配直接 MemoryError。"""
    try:
        import resource

        cpu = max(1, int(limits["cpu_seconds"]))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        # ponytail: macOS RLIMIT_AS 单位为字节且计入解释器自身虚拟空间，
        # pandas 导入本身约占 200-300MB，下限 128MB；默认值由父进程实测校准。
        # 注意：macOS 内核基本不强制 RLIMIT_AS（np.ones(2 亿) 走 mmap 惰性零页
        # 也不会触发），因此另有 _peak_rss_bytes 峰值物理内存事后兜底；
        # Linux 下 RLIMIT_AS 对虚拟地址空间是硬限制，可在分配当下直接 MemoryError。
        memory = max(128, int(limits["memory_mb"])) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        # 32 个 FD：stdin/out/err 之外几乎无余量，socket 连接无法建立
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except ImportError, OSError, ValueError:
        # 非 POSIX 平台退化为仅 wall-clock 超时
        pass


def _peak_rss_bytes() -> int:
    """返回进程峰值物理内存（ru_maxrss）：macOS 单位为字节，Linux 单位为 KB。"""
    import resource
    import sys

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def _write_result(result: dict) -> None:
    blob = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
    out = sys.stdout.buffer
    out.write(MAGIC)
    out.write(struct.pack(">Q", len(blob)))
    out.write(blob)
    out.flush()


def _validate_series(value, df) -> None:
    import numpy as np
    import pandas as pd

    if not isinstance(value, pd.Series):
        raise TypeError(f"factor 必须是 pandas.Series，实际为 {type(value).__name__}")
    if len(value) != len(df):
        raise ValueError(f"factor 长度 {len(value)} 与 df 长度 {len(df)} 不一致")
    if not value.index.equals(df.index):
        raise ValueError("factor 的索引必须与 df 完全一致（逐行对齐，禁止 shift 索引）")
    if value.index.has_duplicates:
        raise ValueError("factor 索引不允许重复")
    if not pd.api.types.is_numeric_dtype(value.dtype):
        raise TypeError("factor 必须是数值类型")
    if int(value.notna().sum()) == 0:
        raise ValueError("factor 至少需要一个非空有限值")
    arr = value.to_numpy(dtype=float, na_value=float("nan"))
    if bool((~np.isnan(arr) & ~np.isfinite(arr)).any()):
        raise ValueError("factor 不允许包含 inf/-inf")


def main() -> int:
    try:
        header = sys.stdin.buffer.read(_HEADER_LEN)
        if len(header) != _HEADER_LEN:
            raise RuntimeError("payload header truncated")
        (payload_len,) = struct.unpack(">Q", header)
        payload = pickle.loads(sys.stdin.buffer.read(payload_len))

        _apply_limits(payload["limits"])
        memory_mb = max(128, int(payload["limits"]["memory_mb"]))
        memory_bytes = memory_mb * 1024 * 1024

        import builtins

        import numpy as np
        import pandas as pd

        safe_builtins = {name: getattr(builtins, name) for name in _SAFE_BUILTINS}
        # open/exec/eval/__import__/getattr 等一律不存在
        globals_ns = {"__builtins__": safe_builtins, "np": np, "pd": pd}
        compiled = compile(payload["code"], "<llm-factor>", "exec")

        series = {}
        for symbol, df in payload["frames"].items():
            # 每个品种独立 locals，防止上一个品种的中间变量串味
            locals_ns = {"df": df}
            exec(compiled, globals_ns, locals_ns)  # 受控白名单代码
            # ponytail 兜底：macOS 不强制 RLIMIT_AS，惰性零页（np.ones 之类）
            # 不触碰物理页就无法被前置拦截，这里用峰值 RSS 做事后拒绝——
            # 内存炸弹仍会短暂占用物理内存，但其结果一定被丢弃、不会进入评估流程。
            used = _peak_rss_bytes()
            if used > memory_bytes:
                raise MemoryError(f"因子代码峰值物理内存约 {used / 1024 / 1024:.0f}MB，超过 {memory_mb}MB 限额")
            _validate_series(locals_ns.get("factor"), df)
            series[symbol] = locals_ns["factor"]

        _write_result({"status": "success", "series": series})
        return 0
    except Exception as exc:  # 子进程内任何异常都回传，不向父进程抛裸异常
        _write_result(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc)[:800],
                "traceback": traceback.format_exc()[-1200:],
            }
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
