"""_meta.json 读写（Task 4 完整实现；本 task 提供桩以让 import 通过）。"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from exchange.binance.archive.kinds import ArchiveKind, MarketType

logger = logging.getLogger(__name__)


def _now_iso_ns() -> str:
    """纳秒精度 ISO 8601 时间戳。"""
    return datetime.now().astimezone().isoformat()


def write_meta(
    save_dir: Path,
    symbol: str,
    kind: ArchiveKind,
    market: MarketType,
    last_added_day: date,
) -> dict:
    """Task 4 完整实现；本 task 占位（写最小有效 JSON 即可）。"""
    save_dir.mkdir(parents=True, exist_ok=True)
    meta_path = save_dir / '_meta.json'
    if not meta_path.exists():
        meta = {
            'symbol': symbol,
            'kind': kind.value,
            'market': market.value,
            'earliest_date': last_added_day.isoformat(),
            'latest_date': last_added_day.isoformat(),
            'total_rows': 0,
            'file_count': 0,
            'corrupt_dates': [],
            'updated_at': _now_iso_ns(),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        return meta
    # 已存在时 Task 4 会重新扫描统计；本 task 直接返回现有内容
    return read_meta(save_dir) or {}


def read_meta(save_dir: Path) -> dict | None:
    """读 _meta.json；不存在返回 None。"""
    meta_path = save_dir / '_meta.json'
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", meta_path, exc)
        return None
