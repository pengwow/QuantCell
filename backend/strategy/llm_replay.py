"""LLM 决策可回放 — 录制 / 回放 provider 包装。

背景：``llm_signal`` 策略的 ``mode='llm'`` 会调用外部 LLM 产出信号，同样的
K 线在回测里重跑可能拿到不同答案（模型温度、服务端版本、网络抖动）。为了让
回测可复现，回测必须只读历史响应，禁止在回测中真的请求 LLM。

两种包装（都是 ``Callable[[str], str]``，与策略的 ``llm_provider`` 签名一致）：

- :class:`RecordingProvider`：paper / live 调用真实 provider，并把
  ``(fingerprint, response)`` 追加写 JSONL；
- :class:`ReplayProvider`：backtest 只从 JSONL 查表，未命中直接抛
  :class:`ReplayMissError`，不回退 heuristic、不返回空串。

文件格式（JSONL，每行一条）::

    {"fingerprint": "<64 hex>", "response": "<LLM 原始回复>"}

同一 fingerprint 在录制时只保留**首次**答案：回放时一个 prompt 只能对应一个
响应，后写会污染已固化的决策（也避免长跑进程重复请求后行数膨胀）。

fingerprint 与 Rust 侧的等价边界
--------------------------------
本模块 ``request_fingerprint`` 对 **原始 prompt 字符串的 UTF-8 字节** 做 sha256；
``axon_quant::decision::fingerprint::request_fingerprint`` 是对 ``DecisionRequest``
结构体做 ``serde_json`` 紧凑序列化（BTreeMap 键有序、无空格、中文不转义）后 sha256。

两者只有在输入字节完全一致时才相等。``llm_signal`` 发出的是自由文本 prompt（其中
收盘价列表是 Python ``repr`` 而不是 JSON），不是 ``DecisionRequest`` JSON，因此
**不等价**：本模块的录制文件不能直接喂给 axon-llm 的 replay 后端，反之亦然。
这里只在 Python 侧保证「同一 prompt → 同一 fingerprint」的录制/回放自洽。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__, LogType.APPLICATION)


class ReplayMissError(Exception):
    """回放请求未命中录制记录。

    显式抛出而不是降级：回测里「查不到的 LLM 决策」等价于结果不可复现，
    静默变成 heuristic 或 Hold 会让回测数字看起来正常但语义错误。
    """


def request_fingerprint(request: str) -> str:
    """prompt → sha256 hex（与 Rust 侧只做算法同构，输入字节不等价，见模块 docstring）。"""
    return hashlib.sha256(request.encode("utf-8")).hexdigest()


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_replay_dir() -> Path:
    """默认录制目录：跟随项目 data 目录约定（backend/data/llm_replay）。

    桌面 sidecar 可用 ``QUANTCELL_LLM_REPLAY_DIR`` 重定向到可写目录。
    """
    override = os.environ.get("QUANTCELL_LLM_REPLAY_DIR")
    if override:
        return Path(override).expanduser()
    return _backend_root() / "data" / "llm_replay"


def _resolve_user_path(raw: str | Path) -> Path:
    """用户给的路径：绝对路径原样，相对路径以 backend 根为基准（不依赖进程 cwd）。"""
    path = Path(raw).expanduser()
    return path if path.is_absolute() else _backend_root() / path


def resolve_replay_path(strategy_name: str, params: dict) -> Path | None:
    """解析回测应读取的录制文件；不存在时返回 None（由调用方决定报错口径）。

    - 策略参数 ``llm_replay_path`` 优先：绝对路径原样使用，相对路径以 backend 根为基准
      （与数据目录同基准，避免依赖进程 cwd）；
    - 未配置时回退到默认目录下的 ``<strategy_name>.jsonl``（便于固定文件复用）。
    """
    raw = params.get("llm_replay_path")
    if raw:
        path = _resolve_user_path(raw)
        return path if path.is_file() else None
    candidate = default_replay_dir() / f"{strategy_name}.jsonl"
    return candidate if candidate.is_file() else None


def new_recording_path(strategy_name: str) -> Path:
    """录制文件名按策略名 + UTC 时间戳区分，避免多次启动互相覆盖。"""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    return default_replay_dir() / f"{strategy_name}_{stamp}.jsonl"


class RecordingProvider:
    """包装真实 provider：调用后追加写一条 ``{fingerprint, response}``。"""

    def __init__(self, inner: Callable[[str], str], path: str | Path):
        self._inner = inner
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 进程重启后继续写同一文件时，已存在的 fingerprint 不再重复落行
        self._seen: set[str] = set()
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                record = self._parse_line(line)
                if record:
                    self._seen.add(record["fingerprint"])

    @staticmethod
    def _parse_line(line: str) -> dict | None:
        """跳过空行；脏行只告警不中断录制（新文件写入以本次为准）。"""
        if not line.strip():
            return None
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(f"[llm_replay] 录制文件存在非法 JSON 行，已跳过: {line[:80]}")
            return None
        if not isinstance(record, dict) or not isinstance(record.get("fingerprint"), str):
            return None
        return record

    def __call__(self, request: str) -> str:
        response = self._inner(request)
        fingerprint = request_fingerprint(request)
        if fingerprint in self._seen:
            return response
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"fingerprint": fingerprint, "response": response}, ensure_ascii=False) + "\n")
            fh.flush()
        self._seen.add(fingerprint)
        return response


class ReplayProvider:
    """从 JSONL 读取 fingerprint→response；未命中抛 :class:`ReplayMissError`。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            msg = f"LLM replay 记录不存在: {self.path}"
            raise ReplayMissError(msg)
        self._records: dict[str, str] = {}
        for lineno, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                msg = f"LLM replay 记录非法 JSON: {self.path}:{lineno}"
                raise ReplayMissError(msg) from e
            fingerprint, response = record.get("fingerprint"), record.get("response")
            if not isinstance(fingerprint, str) or not isinstance(response, str):
                msg = f"LLM replay 记录字段缺失: {self.path}:{lineno}"
                raise ReplayMissError(msg)
            # 重复 fingerprint 保留首条（与录制侧「只写首次」口径一致）
            self._records.setdefault(fingerprint, response)
        self.hits = 0

    def __call__(self, request: str) -> str:
        fingerprint = request_fingerprint(request)
        try:
            response = self._records[fingerprint]
        except KeyError:
            msg = (
                f"LLM replay 未命中: fingerprint={fingerprint} "
                f"(file={self.path}, recorded={len(self._records)} 条)"
            )
            raise ReplayMissError(msg) from None
        self.hits += 1
        return response


def wrap_llm_provider(
    strategy_name: str,
    params: dict,
    run_mode: str,
) -> dict:
    """按运行模式包装 ``llm_provider``，返回新的 params（不修改入参）。

    - 非 ``mode='llm'`` 或没有注入 provider：原样返回，既有 heuristic / 降级语义不变；
    - ``backtest``：``ReplayProvider``，记录文件缺失即抛 :class:`ReplayMissError`；
    - ``paper`` / ``live``：``RecordingProvider``，路径取 ``llm_replay_path``，
      未配置时按策略名 + 时间戳在默认目录新建。

    Raises:
        ReplayMissError: 回测缺少录制文件，或运行模式未知。
    """
    if params.get("mode") != "llm":
        return params
    inner = params.get("llm_provider")
    if inner is None:
        # 没有 provider 时策略原有语义就是 Hold(no_llm_provider)，此处不改变行为
        return params

    out = dict(params)
    if run_mode == "backtest":
        path = resolve_replay_path(strategy_name, params)
        if path is None or not path.is_file():
            msg = (
                "LLM 策略回测必须提供 replay 记录(llm_replay_path)，"
                "禁止静默降级为 heuristic；当前未找到可用的录制文件"
            )
            raise ReplayMissError(msg)
        out["llm_provider"] = ReplayProvider(path)
        logger.info(f"[llm_replay] 回测命中回放: strategy={strategy_name} file={path}")
    elif run_mode in ("paper", "live"):
        path = (
            _resolve_user_path(params["llm_replay_path"])
            if params.get("llm_replay_path")
            else new_recording_path(strategy_name)
        )
        out["llm_provider"] = RecordingProvider(inner, path)
        logger.info(f"[llm_replay] {run_mode} 开始录制: strategy={strategy_name} file={path}")
    else:
        msg = f"未知运行模式: {run_mode}（可选 backtest / paper / live）"
        raise ValueError(msg)
    return out
