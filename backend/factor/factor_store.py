"""自定义因子 JSON 持久化（backend/data/factor/custom_factors.json）。

写盘使用「临时文件 + os.replace」原子替换，避免半写损坏；损坏文件按空库加载。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "factor" / "custom_factors.json"


class FactorStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        self._data = self._load()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"自定义因子文件损坏，按空库加载: {e}")
            return {}

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def all(self) -> dict[str, str]:
        return dict(self._data)

    def upsert(self, name: str, expression: str) -> None:
        self._data[name] = expression
        self._flush()

    def delete(self, name: str) -> bool:
        if name not in self._data:
            return False
        del self._data[name]
        self._flush()
        return True
