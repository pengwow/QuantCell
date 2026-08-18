"""衍生数据（fundingRate / openInterest）浏览业务层。

目录结构: data/source/{kind}/{market}/{symbol}/
与 archive 的 market/kind/symbol 相反；其余 parquet 读写、元数据逻辑相近。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 合法衍生数据种类
VALID_DERIV_KINDS = {"fundingRate", "openInterest"}
# 合法 market
VALID_MARKETS = {"spot", "um", "cm"}


def _validate(kind: str, market: str) -> None:
    if kind not in VALID_DERIV_KINDS:
        msg = f"非法 deriv kind: {kind!r} (must be one of {sorted(VALID_DERIV_KINDS)})"
        raise ValueError(msg)
    if market not in VALID_MARKETS:
        msg = f"非法 market: {market!r} (must be one of {sorted(VALID_MARKETS)})"
        raise ValueError(msg)


def _symbol_dir(base_dir: Path, kind: str, market: str, symbol: str) -> Path:
    """衍生数据目录: base_dir/kind/market/symbol/"""
    return base_dir / kind / market / symbol


class DerivService:
    """衍生数据浏览服务（不做下载，只负责 list / meta / query / delete）。"""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    # —— symbols 列表 ——
    def list_symbols(self, kind: str, market: str) -> list[str]:
        _validate(kind, market)
        market_dir = self.base_dir / kind / market
        if not market_dir.exists():
            return []
        return sorted(p.name for p in market_dir.iterdir() if p.is_dir() and any(p.glob("*.parquet")))

    # —— 元数据（从 parquet 文件推断，不强制要求 _meta.json）——
    def get_meta(self, kind: str, market: str, symbol: str) -> dict | None:
        _validate(kind, market)
        sym_dir = _symbol_dir(self.base_dir, kind, market, symbol)
        if not sym_dir.exists():
            return None

        parquet_files = sorted(sym_dir.glob("*.parquet"))
        if not parquet_files:
            return None

        total_rows = 0
        earliest = None
        latest = None
        for pf in parquet_files:
            try:
                df = pd.read_parquet(pf)
                if df.empty:
                    continue
                total_rows += len(df)
                # timestamp 存在则统计时间范围
                if "timestamp" in df.columns:
                    ts = df["timestamp"].iloc[0]
                    ts_first = int(ts) // 1_000_000 if int(ts) > 10**14 else int(ts)
                    if earliest is None or ts_first < earliest:
                        earliest = ts_first
                    ts_last_raw = int(df["timestamp"].iloc[-1])
                    ts_last = ts_last_raw // 1_000_000 if ts_last_raw > 10**14 else ts_last_raw
                    if latest is None or ts_last > latest:
                        latest = ts_last
            except Exception as exc:
                logger.warning(f"读取 parquet 元信息失败 {pf}: {exc}")

        # 日期范围从文件名推断（更稳定）
        import re

        dates = []
        for pf in parquet_files:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", pf.name) or re.search(r"(\d{8})", pf.name)
            if m:
                s = m.group(1)
                dates.append(s if "-" in s else f"{s[:4]}-{s[4:6]}-{s[6:]}")

        return {
            "symbol": symbol,
            "kind": kind,
            "market": market,
            "earliest_date": min(dates) if dates else None,
            "latest_date": max(dates) if dates else None,
            "total_rows": total_rows,
            "file_count": len(parquet_files),
            "corrupt_dates": [],
            "updated_at": None,
            # 额外统计
            "_earliest_ts_ms": earliest,
            "_latest_ts_ms": latest,
        }

    # —— 分页查询 parquet 数据 ——
    def query_data(
        self,
        kind: str,
        market: str,
        symbol: str,
        start_time: int,  # 毫秒
        end_time: int,  # 毫秒
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        _validate(kind, market)
        sym_dir = _symbol_dir(self.base_dir, kind, market, symbol)
        if not sym_dir.exists():
            return {"total": 0, "rows": [], "truncated": False}

        parquet_files = sorted(sym_dir.glob("*.parquet"))
        if not parquet_files:
            return {"total": 0, "rows": [], "truncated": False}

        dfs: list[pd.DataFrame] = []
        for pf in parquet_files:
            try:
                dfs.append(pd.read_parquet(pf))
            except Exception as exc:
                logger.warning(f"跳过损坏的 parquet {pf}: {exc}")

        if not dfs:
            return {"total": 0, "rows": [], "truncated": False}

        df = pd.concat(dfs, ignore_index=True)

        # 按 timestamp 过滤（兼容纳秒 / 毫秒 / 秒）
        if "timestamp" in df.columns and not df.empty:
            sample = int(df["timestamp"].iloc[0])
            if sample > 10**14:  # 纳秒 -> 毫秒
                df["_ts_ms"] = df["timestamp"].astype("int64") // 1_000_000
            elif sample > 10**10:  # 毫秒
                df["_ts_ms"] = df["timestamp"].astype("int64")
            else:  # 秒 -> 毫秒
                df["_ts_ms"] = df["timestamp"].astype("int64") * 1_000
            df = df[(df["_ts_ms"] >= start_time) & (df["_ts_ms"] <= end_time)]
            df = df.drop(columns=["_ts_ms"])

        total = len(df)
        # 排序: 有 timestamp 按 timestamp 升序
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp", kind="mergesort")

        truncated = False
        if total > limit + offset:
            truncated = True

        df_page = df.iloc[offset : offset + limit]
        rows: list[dict] = df_page.where(pd.notnull(df_page), None).to_dict(orient="records")

        return {"total": total, "rows": rows, "truncated": truncated}

    # —— 删除 ——
    def delete_data(self, kind: str, market: str, symbol: str) -> Path | None:
        _validate(kind, market)
        sym_dir = _symbol_dir(self.base_dir, kind, market, symbol)
        if sym_dir.exists():
            shutil.rmtree(sym_dir)
            logger.warning(f"已删除衍生数据目录: {sym_dir}")
            return sym_dir
        return None
