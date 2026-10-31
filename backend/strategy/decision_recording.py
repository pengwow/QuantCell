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
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


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
    ):
        self._inner = inner
        self.path = Path(path)
        self.s2_mode = s2_mode
        self._replay = replay_table
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 进程重启后继续写同一文件时，已存在的 fingerprint 不再重复落行
        self._seen: set[str] = set()
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                record = _parse_line(line)
                if record:
                    self._seen.add(record["fingerprint"])

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
        self._seen.add(fp)
        record = {
            "fingerprint": fp,
            "decision": decision,
            "state": state,
            "questions": questions,
            "ts": _iso8601_ns(),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
