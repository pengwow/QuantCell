"""自定义因子 JSON 持久化（backend/data/factor/custom_factors.json）。

写盘使用「临时文件 + os.replace」原子替换，避免半写损坏；损坏文件按空库加载。
条目格式：{name: {"expression": str, "description": str}}；
兼容旧格式 {name: "expression"}（加载时自动升级，description 视为空）。
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

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"自定义因子文件损坏，按空库加载: {e}")
            return {}
        if not isinstance(data, dict):
            return {}
        # 旧格式 {name: "expr"} 升级为 {name: {expression, description}}
        out: dict[str, dict[str, str]] = {}
        for k, v in data.items():
            if isinstance(v, str):
                out[str(k)] = {"expression": v, "description": ""}
            elif isinstance(v, dict):
                out[str(k)] = {
                    "expression": str(v.get("expression", "")),
                    "description": str(v.get("description", "")),
                }
        return out

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def all(self) -> dict[str, str]:
        """表达式映射 {name: expression}（保持旧契约，供因子引擎消费）。"""
        return {k: v["expression"] for k, v in self._data.items()}

    def description_of(self, name: str) -> str:
        """因子描述；不存在或未设置返回空串。"""
        return self._data.get(name, {}).get("description", "")

    def upsert(self, name: str, expression: str, description: str = "") -> None:
        self._data[name] = {"expression": expression, "description": description}
        self._flush()

    def delete(self, name: str) -> bool:
        if name not in self._data:
            return False
        del self._data[name]
        self._flush()
        return True
