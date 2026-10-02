"""合成因子持久化（backend/data/factor/composite_factors.json）。

合成因子（method=ic_zscore_v1）= 多个代码因子面板经 IC 加权 zscore 组合，
与代码因子（code_factors.json）、表达式因子（custom_factors.json）分库：
- 代码因子走单代码沙箱；表达式走 AST 白名单；合成因子是「冻结权重 + 冻结
  时序统计」的多代码组合，三条执行路径不可互相伪装。
- 写盘使用「临时文件 + os.replace」原子替换；损坏文件按空库加载（同 code_store）。

spec 结构：
{name: {description, method, train_window:{start,end,interval,candle_type},
        constituents:[{code, weight, ts_stats:{symbol:{mean,std}}}],
        created_at, provenance}}
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

DEFAULT_COMPOSITE_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "factor" / "composite_factors.json"

COMPOSITE_METHOD = "ic_zscore_v1"


class CompositeFactorStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_COMPOSITE_STORE_PATH
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
                # 仅接纳结构完整的条目（至少含 constituents 列表）
                if isinstance(v, dict) and isinstance(v.get("constituents"), list):
                    loaded[str(k)] = v
            return loaded
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"合成因子文件损坏，按空库加载: {exc}")
            return {}

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def all(self) -> dict[str, dict[str, Any]]:
        return dict(self._data)

    def list(self) -> dict[str, dict[str, Any]]:
        return self.all()

    def get(self, name: str) -> dict[str, Any] | None:
        return self._data.get(name)

    def names(self) -> list[str]:
        return list(self._data)

    def exists(self, name: str) -> bool:
        return name in self._data

    def upsert(
        self,
        name: str,
        *,
        description: str = "",
        train_window: dict[str, Any],
        constituents: list[dict[str, Any]],
        provenance: dict[str, Any] | None = None,
        method: str = COMPOSITE_METHOD,
    ) -> None:
        existed = self._data.get(name)
        self._data[name] = {
            "description": description,
            "method": method,
            "train_window": train_window,
            "constituents": constituents,
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
