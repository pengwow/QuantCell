"""代码因子持久化（backend/data/factor/code_factors.json）。

结构：{name: {"code", "description", "provenance", "created_at"}}。
与表达式因子（custom_factors.json）分库：表达式走 AST 白名单引擎，
代码因子走子进程沙箱，两条执行路径不可互相伪装。
写盘使用「临时文件 + os.replace」原子替换；损坏文件按空库加载。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

DEFAULT_CODE_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "factor" / "code_factors.json"


class CodeFactorStore:
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
            return {str(k): v for k, v in data.items() if isinstance(v, dict) and "code" in v}
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
    ) -> None:
        existed = self._data.get(name)
        self._data[name] = {
            "code": code,
            "description": description,
            "provenance": provenance or (existed or {}).get("provenance", {}),
            "created_at": (existed or {}).get("created_at") or datetime.now(UTC).isoformat(),
        }
        self._flush()

    def delete(self, name: str) -> bool:
        if name not in self._data:
            return False
        del self._data[name]
        self._flush()
        return True
