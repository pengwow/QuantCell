"""代码因子持久化（backend/data/factor/code_factors.json）。

结构：{name: {"code", "code_hash", "description", "provenance", "created_at"}}。
与表达式因子（custom_factors.json）分库：表达式走 AST 白名单引擎，
代码因子走子进程沙箱，两条执行路径不可互相伪装。
写盘使用「临时文件 + os.replace」原子替换；损坏文件按空库加载。

code_hash 的规范化口径在本模块定义，是入库去重与 LLM 挖掘内存去重的
**单一真相源**（factor.llm_miner 从此处导入复用）；口径必须一致，
改动需同步两处调用方并回归 test_llm_miner 的去重用例。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

DEFAULT_CODE_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "factor" / "code_factors.json"


def normalize_code(code: str) -> str:
    """代码规范化：整体去首尾空白、丢弃空行、每行去行尾空白。

    口径与 LLM 挖掘去重完全一致（本函数为单一真相源，
    factor.llm_miner 导入复用；改动需同步评估两处去重行为）。
    """
    return "\n".join(line.rstrip() for line in code.strip().splitlines() if line.strip())


def code_hash(code: str) -> str:
    """规范化代码的 sha256 前 16 位；仅空行/行尾空白差异的同构代码同 hash。

    口径与 LLM 挖掘内存去重共用（factor.llm_miner 从本模块导入），
    改动需同步并回归 test_llm_miner 去重用例。
    """
    return hashlib.sha256(normalize_code(code).encode("utf-8")).hexdigest()[:16]


class CodeFactorStore:
    # 别名暴露模块级 code_hash：upsert 的同名参数会在方法体内遮蔽全局函数名
    _compute_hash = staticmethod(code_hash)

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_CODE_STORE_PATH
        self._data = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            loaded: dict[str, dict[str, Any]] = {}
            for k, v in data.items():
                if not (isinstance(v, dict) and "code" in v):
                    continue
                # 老格式条目缺 code_hash：按同口径补算放入内存，不强制回写，
                # 后续 upsert 时自然落盘
                if not v.get("code_hash"):
                    v = {**v, "code_hash": code_hash(v["code"])}
                loaded[str(k)] = v
            return loaded
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"代码因子文件损坏，按空库加载: {exc}")
            return {}

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def all(self) -> dict[str, dict[str, Any]]:
        return dict(self._data)

    def get(self, name: str) -> dict[str, Any] | None:
        return self._data.get(name)

    def code_of(self, name: str) -> str | None:
        entry = self._data.get(name)
        return entry["code"] if entry else None

    def upsert(
        self,
        name: str,
        code: str,
        description: str = "",
        provenance: dict[str, Any] | None = None,
        code_hash: str | None = None,
    ) -> None:
        existed = self._data.get(name)
        self._data[name] = {
            "code": code,
            "code_hash": code_hash or self._compute_hash(code),
            "description": description,
            "provenance": provenance or (existed or {}).get("provenance", {}),
            "created_at": (existed or {}).get("created_at") or datetime.now(UTC).isoformat(),
        }
        self._flush()

    def find_by_hash(self, h: str, exclude_name: str | None = None) -> str | None:
        """返回 code_hash 匹配的因子名；无匹配返回 None。

        exclude_name 跳过指定因子（同名覆盖保存时排除自身，避免误判重复）。
        """
        for name, entry in self._data.items():
            if name == exclude_name:
                continue
            if entry.get("code_hash") == h:
                return name
        return None

    def delete(self, name: str) -> bool:
        if name not in self._data:
            return False
        del self._data[name]
        self._flush()
        return True
