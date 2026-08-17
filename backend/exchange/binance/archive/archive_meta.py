"""`_meta.json` 读写。

每个 (market, kind, symbol) 目录下一份 `_meta.json`, 结构 (spec §3.1):
    {
      "symbol": "BTCUSDT",
      "kind": "aggTrades",
      "market": "spot",
      "earliest_date": "2017-08-17",
      "latest_date": "2026-07-15",
      "total_rows": 52345678,
      "file_count": 3207,
      "corrupt_dates": [],
      "updated_at": "2026-07-15T08:00:00.000000000+08:00"
    }

时间戳遵循 ISO 8601 (RFC 3339) 9 位纳秒精度, 保留所有数字 + 时区.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from exchange.binance.archive.kinds import ArchiveKind, MarketType

logger = logging.getLogger(__name__)

# 文件名中末尾日期段的正则 (兼容 "BTCUSDT-aggTrades-2024-12-01" 与
# "BTCUSDT-markPriceKlines-1h-2024-12-01" 两种形式: 取末尾 YYYY-MM-DD)
_DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})$')

# 文件名结尾的日期段: 形如 "-YYYY-MM-DD"
_FILENAME_DATE_RE = re.compile(r'-(\d{4})-(\d{2})-(\d{2})(?=\.parquet$)')


def _now_iso_ns() -> str:
    """纳秒精度 ISO 8601 时间戳 (含时区, 9 位小数).

    Python `datetime.isoformat()` 只支持微秒精度 (6 位), 这里手动把微秒段补齐到纳秒 (9 位),
    保留尾随零以严格匹配 spec §3.1. 注意时区偏移在尾部, 必须插在时区之前.
    """
    now = datetime.now(timezone.utc).astimezone()
    # 用 microseconds 拿到形如 "2026-07-16T20:00:00.123456+08:00" 的字符串
    micro = now.isoformat(timespec='microseconds')
    # 拆出日期时间段 + 时区段 (最后一个 + 或 - 出现处)
    tz_idx = max(micro.rfind('+'), micro.rfind('-') - (1 if micro.rfind('-') > 10 else 0))
    # 简化: 时区段必定以 "+HH:MM" / "-HH:MM" / "Z" 结尾
    # 找到 ".123456" 的位置
    dot = micro.index('.')
    # 时区起点: micro[dot+7] 起是时区 (因为 .123456 占 7 字符)
    return f"{micro[:dot + 7]}000{micro[dot + 7:]}"


def scan_parquet_files(save_dir: Path) -> list[tuple[date, Path]]:
    """扫描 `save_dir` 下所有 `*.parquet`, 从文件名提取日期, 返回 [(date, path), ...].

    兼容 interval 段 (e.g. `BTCUSDT-markPriceKlines-1h-2024-12-01.parquet`).
    跳过无法解析日期的文件.
    """
    if not save_dir.exists():
        return []
    results: list[tuple[date, Path]] = []
    for p in save_dir.glob('*.parquet'):
        m = _FILENAME_DATE_RE.search(p.name)
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        results.append((d, p))
    return results


def _scan_rows_and_dates(save_dir: Path) -> tuple[list[date], int, int]:
    """扫描 parquet 目录, 返回 (所有日期列表, 文件数, 总行数).

    用 `pyarrow.parquet.ParquetFile` 只读 metadata, 不加载数据, 适合大文件.
    """
    pairs = scan_parquet_files(save_dir)
    total_rows = 0
    for _, p in pairs:
        try:
            md = pq.read_metadata(p)
            total_rows += md.num_rows
        except Exception as exc:  # noqa: BLE001 — parquet 文件可能损坏
            logger.warning("Skip read metadata for %s: %s", p.name, exc)
    dates = [d for d, _ in pairs]
    return dates, len(pairs), total_rows


def read_meta(save_dir: Path) -> dict[str, Any] | None:
    """读 `_meta.json`; 不存在 / 损坏返回 `None` 并 log warn."""
    meta_path = save_dir / '_meta.json'
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", meta_path, exc)
        return None


def _build_meta(
    save_dir: Path,
    symbol: str,
    kind: ArchiveKind,
    market: MarketType,
) -> dict[str, Any]:
    """基于目录扫描结果构造 meta dict; 保留已有 `corrupt_dates` 和日期范围."""
    existing = read_meta(save_dir) or {}
    dates, file_count, total_rows = _scan_rows_and_dates(save_dir)

    if dates:
        earliest = min(dates).isoformat()
        latest = max(dates).isoformat()
    else:
        # 没有 parquet 文件, 沿用现有范围 (避免把空目录重置成 1970)
        earliest = existing.get('earliest_date')
        latest = existing.get('latest_date')

    # corrupt_dates 字段必须保留 (即使后续重写 _meta.json 也不丢)
    corrupt = list(existing.get('corrupt_dates') or [])

    meta: dict[str, Any] = {
        'symbol': symbol,
        'kind': kind.value,
        'market': market.value,
        'earliest_date': earliest,
        'latest_date': latest,
        'total_rows': total_rows,
        'file_count': file_count,
        'corrupt_dates': corrupt,
        'updated_at': _now_iso_ns(),
    }
    return meta


def write_meta(
    save_dir: Path,
    symbol: str,
    kind: ArchiveKind,
    market: MarketType,
    last_added_day: date,
) -> dict[str, Any]:
    """扫描目录并重写 `_meta.json`. 总是基于最新 parquet 列表重算 stats.

    `last_added_day` 用于调用方语义 (最近一次新增的日期), 不写入文件.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    meta = _build_meta(save_dir, symbol, kind, market)
    meta_path = save_dir / '_meta.json'
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def update_meta_after_corrupt(save_dir: Path, day: date) -> dict[str, Any] | None:
    """把 `day.isoformat()` 加入 `_meta.json.corrupt_dates` 列表 (去重, 保序).

    若 `_meta.json` 不存在, 先扫描目录建立基础 meta, 再追加 corrupt 日期.
    返回更新后的 meta dict (失败返回 None).
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    meta_path = save_dir / '_meta.json'
    if not meta_path.exists():
        # 无元数据时尽量建立基础信息; 拿不到 symbol/kind/market 就用空值占位
        meta = {
            'symbol': '',
            'kind': '',
            'market': '',
            'earliest_date': day.isoformat(),
            'latest_date': day.isoformat(),
            'total_rows': 0,
            'file_count': 0,
            'corrupt_dates': [day.isoformat()],
            'updated_at': _now_iso_ns(),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        return meta

    existing = read_meta(save_dir) or {}
    corrupt = list(existing.get('corrupt_dates') or [])
    day_str = day.isoformat()
    if day_str not in corrupt:
        corrupt.append(day_str)
    existing['corrupt_dates'] = corrupt
    existing['updated_at'] = _now_iso_ns()
    meta_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    return existing
