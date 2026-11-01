"""cascade 决策录制与策略层查表复跑。

格式为 QuantCell 自有契约（不经 Rust ReplayDecisionBackend）：
PyCascadeLayer.decide 只返回 CascadeDecision，拿不到 S1 原始 DecisionResponse，
因此录制 decision 本体，复跑时在策略层按下标查表直出。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# ponytail: 运行期去重集合的上限。超长回测（>20 万 bar）下放弃运行期去重，
# 以「不再增长内存」优先；已存在条目的去重仍由启动时加载的集合保证。
_MAX_DEDUPE_FINGERPRINTS = 200_000


def request_fingerprint(state: dict, questions: dict) -> str:
    """state+questions 的规范化指纹（键排序、紧凑 JSON、UTF-8 原文）。

    录制与复跑共用同一实现，自洽无跨语言浮点风险；
    与 axon-llm fingerprint.rs 的 serde_json::to_string 规则等价，便于未来迁移。
    """
    canonical = json.dumps(
        {"state": state, "questions": questions},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_replay_dir() -> Path:
    """默认录制目录：backend/data/decision_replay（环境变量可重定向）"""
    override = os.environ.get("QUANTCELL_DECISION_REPLAY_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "decision_replay"


def _iso8601_ns() -> str:
    """ISO 8601 纳秒精度时间戳（9 位小数，UTC）"""
    ns = time.time_ns()
    dt = datetime.fromtimestamp(ns // 1_000_000_000, tz=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{ns % 1_000_000_000:09d}Z"


def _parse_line(line: str) -> dict | None:
    """跳过空行；脏行只告警不中断（新文件写入以本次为准）"""
    if not line.strip():
        return None
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        logger.warning(f"[cascade] 录制文件存在脏行，已跳过: {line[:80]}")
        return None
    if not isinstance(record, dict) or not isinstance(record.get("fingerprint"), str):
        logger.warning(f"[cascade] 录制条目缺 fingerprint，已跳过: {line[:80]}")
        return None
    return record


class DecisionReplayTable:
    """fingerprint → 录制 decision 的只读查表（同指纹首条为准）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            msg = f"decision replay 记录不存在: {self.path}"
            raise FileNotFoundError(msg)
        self._records: dict[str, dict] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            record = _parse_line(line)
            if record:
                decision = record.get("decision")
                if isinstance(decision, dict):
                    self._records.setdefault(record["fingerprint"], decision)

    def lookup(self, fingerprint: str) -> dict | None:
        return self._records.get(fingerprint)

    def fingerprints(self) -> set[str]:
        """已加载的全部指纹（供录制侧复用，避免二次读同一文件）"""
        return set(self._records)

    def __len__(self) -> int:
        return len(self._records)


class RecordingCascadeLayer:
    """包装 cascade layer：每次决策写一行录制；s2_mode=replay 时用录制覆盖 fallback。"""

    def __init__(
        self,
        inner: Any,
        path: str | Path,
        s2_mode: str = "live",
        replay_table: DecisionReplayTable | None = None,
        meta: dict | None = None,
    ):
        self._inner = inner
        self.path = Path(path)
        self.s2_mode = s2_mode
        self._replay = replay_table
        # 录制来源标注（如 s1_api_host / s1_model）：不同 S1 服务对 confidence 的语义可能不同
        # （本地适配层用 answer_confidence，官方 laya-serve 用 1-归一化熵），
        # 落盘后可分辨新旧数据来源，避免跨来源比较门限分布
        self._meta = dict(meta or {})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 进程重启后继续写同一文件时，已存在的 fingerprint 不再重复落行；
        # 若调用方已加载 replay_table（同一文件），直接复用其指纹集合，避免二次读盘
        if replay_table is not None:
            self._seen: set[str] = replay_table.fingerprints()
        else:
            self._seen = set()
            if self.path.is_file():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    record = _parse_line(line)
                    if record:
                        self._seen.add(record["fingerprint"])
        # 长生命周期句柄：回测逐 bar 写盘，避免每 bar open/close 的 syscall 开销
        self._writer: Any = None

    def decide(self, state: dict, questions: dict) -> dict:
        fp = request_fingerprint(state, questions)
        decision = self._inner.decide(state, questions)

        if self.s2_mode == "replay" and decision.get("source") == "fallback":
            recorded = self._replay.lookup(fp) if self._replay else None
            if recorded and recorded.get("source") == "fallback":
                decision = dict(recorded)
                decision["fallback_reason"] = f"{decision.get('fallback_reason') or 'fallback'}|s2_replay"
            else:
                logger.warning(f"[cascade] s2_replay_miss fingerprint={fp}，保留规则兜底结果")

        self._append(fp, state, questions, decision)
        return decision

    def _append(self, fp: str, state: dict, questions: dict, decision: dict) -> None:
        if fp in self._seen:
            return
        if len(self._seen) < _MAX_DEDUPE_FINGERPRINTS:
            self._seen.add(fp)
        record = {
            "fingerprint": fp,
            "decision": decision,
            "state": state,
            "questions": questions,
            "ts": _iso8601_ns(),
        }
        if self._meta:
            record["meta"] = self._meta
        if self._writer is None:
            self._writer = self.path.open("a", encoding="utf-8")
        self._writer.write(json.dumps(record, ensure_ascii=False) + "\n")
        # 每行 flush：审计/复跑依赖落盘，崩溃最多丢当前这一行
        self._writer.flush()

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def __del__(self) -> None:
        # __init__ 中途抛错时 _writer 可能未建立，用 getattr 防御
        writer = getattr(self, "_writer", None)
        if writer is not None:
            writer.close()
