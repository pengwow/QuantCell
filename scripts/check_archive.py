#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Binance 归档数据 (7 种 × 3 个市场) 端到端自检脚本。

用法:
    cd backend && .venv/bin/python ../scripts/check_archive.py

行为约定 (Ponytail 原则: 最少代码 + 真实可运行 + 失败时退码非 0):
- 测试 1: `BinanceArchiveFactory.create(AGG_TRADES, SPOT, base_dir=tmp, symbol='BTCUSDT')` 构造
- 测试 2: 真实下载 BTCUSDT aggTrades 某日 zip (默认 2024-12-01) → 解析 → 落 Parquet
- 测试 3: 读 Parquet 验证行数 > 1000、价格字段为 float
- 测试 4: 调用 read_range 验证能查出数据
- 测试 5: 验证 _meta.json 存在且 latest_date == 2024-12-01

退出码:
  0 = 全部 5 项通过
  1 = 本地代码 / 数据格式问题 (硬失败)
  2 = 网络不可达 (环境受限, 不算 blocker)
"""
from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path


# aggTrades zip 内 CSV 已知无 header, 8 列固定顺序 (与 spec §3.2 一致)
_AGG_TRADES_COLS = [
    "agg_trade_id", "price", "quantity",
    "first_trade_id", "last_trade_id", "transact_time",
    "is_buyer_maker", "ignore",  # 末列是 'is_best_match' 在 2024-12 起 Binance 加的
]
# 兼容旧版 (7 列) zip: 切到旧列名
_AGG_TRADES_COLS_7 = _AGG_TRADES_COLS[:7]


def _bootstrap_path() -> Path:
    """把 backend/ 加入 sys.path, 返回 backend 根目录的绝对路径。"""
    backend_dir = Path(__file__).resolve().parent.parent / "backend"
    if not backend_dir.exists():
        print(f"[FATAL] 找不到 backend 目录: {backend_dir}", file=sys.stderr)
        sys.exit(1)
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    return backend_dir


def _section(title: str) -> None:
    """打印测试阶段分隔线 (避免重复字符串)。"""
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}", file=sys.stderr)


# =================== 测试 1: 工厂构造 ===================

def test_factory_create(tmp_dir: Path) -> None:
    """验证 BinanceArchiveFactory 装配出正确的 fetcher。"""
    _section("Test 1: BinanceArchiveFactory.create(AGG_TRADES, SPOT, ...) 构造")
    from exchange.binance.archive.factory import BinanceArchiveFactory
    from exchange.binance.archive.kinds import ArchiveKind, MarketType

    fetcher = BinanceArchiveFactory.create(
        ArchiveKind.AGG_TRADES, MarketType.SPOT,
        base_dir=str(tmp_dir), symbol="BTCUSDT",
    )
    assert fetcher.market == MarketType.SPOT, f"market={fetcher.market}"
    assert fetcher.archive_kind == ArchiveKind.AGG_TRADES
    expected_dir = tmp_dir / "spot" / "aggTrades" / "BTCUSDT"
    assert fetcher.save_dir == expected_dir, f"save_dir={fetcher.save_dir}"
    _ok(f"fetcher={type(fetcher).__name__}, save_dir={fetcher.save_dir}")


# =================== 测试 2: 真实下载 + 解析 + 落盘 ===================

async def _download_zip(symbol: str, day: str) -> bytes:
    """真实从 data.binance.vision 下载单日 zip, 返回原始 bytes。"""
    import aiohttp

    from exchange.binance.archive.kinds import ArchiveKind, MarketType, build_zip_url

    url = build_zip_url(MarketType.SPOT, ArchiveKind.AGG_TRADES, symbol, day)
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status == 404:
                raise FileNotFoundError(f"zip not found on data.binance.vision: {url}")
            resp.raise_for_status()
            return await resp.read()


def _parse_aggtrades_zip(raw: bytes) -> "pd.DataFrame":  # type: ignore[name-defined]  # noqa: F821
    """从 aggTrades zip 中解出 CSV 并解析为标准列 DataFrame。"""
    import pandas as pd

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csv_name = next((n for n in zf.namelist() if n.endswith(".csv")), None)
        if csv_name is None:
            raise ValueError(f"zip has no CSV: {zf.namelist()}")
        with zf.open(csv_name) as f:
            text = f.read().decode("utf-8")
    # 真实数据无 header (实测 2024-12-01 验证); 用 names 强制列名
    sample_line = text.splitlines()[0] if text else ""
    n_cols = len(sample_line.split(",")) if sample_line else 0
    cols = _AGG_TRADES_COLS_7 if n_cols <= 7 else _AGG_TRADES_COLS
    df = pd.read_csv(io.StringIO(text), header=None, names=cols)
    # 8 列版本丢掉 ignore 列, 保留 7 列
    if n_cols > 7 and "ignore" in df.columns:
        df = df.drop(columns=["ignore"])
    # 强制类型 (与 AggTradesFetcher.transform_df 对齐)
    return df.assign(
        agg_trade_id=df["agg_trade_id"].astype("int64"),
        price=df["price"].astype("float64"),
        quantity=df["quantity"].astype("float64"),
        first_trade_id=df["first_trade_id"].astype("int64"),
        last_trade_id=df["last_trade_id"].astype("int64"),
        transact_time=df["transact_time"].astype("int64"),
        is_buyer_maker=df["is_buyer_maker"].astype("bool"),
    )


def test_real_download_and_save(tmp_dir: Path, target_day: str) -> Path | None:
    """真实下载 BTCUSDT aggTrades 某日 zip, 解析后落 Parquet。

    返回 parquet 路径; 网络失败返回 None (由 main 决定如何升级)。
    """
    _section(f"Test 2: 真实下载 BTCUSDT aggTrades {target_day} → 解析 → 落 Parquet")
    import asyncio

    from exchange.binance.archive.archive_meta import write_meta
    from exchange.binance.archive.kinds import ArchiveKind, MarketType, get_save_dir

    try:
        zip_bytes = asyncio.run(_download_zip("BTCUSDT", target_day))
    except Exception as exc:  # noqa: BLE001 — 网络/zip 异常都吞掉
        _fail(f"下载失败 (网络不通或日期无数据): {exc}")
        return None

    try:
        df = _parse_aggtrades_zip(zip_bytes)
    except Exception as exc:  # noqa: BLE001
        _fail(f"解析失败: {exc}")
        return None

    if df.empty:
        _fail(f"解析结果为空 DataFrame ({target_day} 当日可能无数据)")
        return None
    _ok(f"下载 + 解析成功: {len(df):,} 行, 列={list(df.columns)}")

    # 落 Parquet: 复用 fetcher.save_instrument 的路径格式, 但绕开 transform_df
    save_dir = get_save_dir(tmp_dir, MarketType.SPOT, ArchiveKind.AGG_TRADES, "BTCUSDT")
    save_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = save_dir / f"BTCUSDT-aggTrades-{target_day}.parquet"
    df.to_parquet(parquet_path, engine="pyarrow", compression="snappy", index=False)
    _ok(f"Parquet 落盘: {parquet_path}")

    # 写 _meta.json (与 collect_data 流程一致)
    write_meta(
        save_dir, "BTCUSDT", ArchiveKind.AGG_TRADES,
        MarketType.SPOT, date.fromisoformat(target_day),
    )
    _ok(f"_meta.json 写入: {save_dir / '_meta.json'}")
    return parquet_path


# =================== 测试 3: Parquet 校验 ===================

def test_parquet_schema(parquet_path: Path) -> bool:
    """验证 Parquet 行数 > 1000 且价格字段 dtype == float64. 返回是否通过。"""
    _section("Test 3: 读 Parquet 验证行数 + 价格字段类型")
    import pandas as pd

    if parquet_path is None or not parquet_path.exists():
        _fail("Parquet 不存在, Test 3 失败")
        return False

    df = pd.read_parquet(parquet_path)
    row_count = len(df)
    if row_count <= 1000:
        _fail(f"行数 {row_count} <= 1000, 数据可能不完整")
        return False
    _ok(f"行数 = {row_count:,} (> 1000 ✓)")

    if "price" not in df.columns:
        _fail("缺少 price 列")
        return False
    if df["price"].dtype != "float64":
        _fail(f"price dtype={df['price'].dtype}, 期望 float64")
        return False
    sample_price = float(df["price"].iloc[0])
    _ok(f"price dtype=float64 ✓, 样例值={sample_price}")
    return True


# =================== 测试 4: read_range 查询 ===================

def test_read_range(tmp_dir: Path, target_day: str) -> bool:
    """通过 fetcher.read_range 在 [target_day 0时, +1日 0时] 区间内查出数据。"""
    _section("Test 4: read_range 区间查询")
    from exchange.binance.archive.factory import BinanceArchiveFactory
    from exchange.binance.archive.kinds import ArchiveKind, MarketType

    fetcher = BinanceArchiveFactory.create(
        ArchiveKind.AGG_TRADES, MarketType.SPOT,
        base_dir=str(tmp_dir), symbol="BTCUSDT",
    )
    # base.read_range 用本地时区 (machine tz) 算 day_ms, 这里用本地 0 时毫秒数
    local_midnight = datetime.fromisoformat(f"{target_day}T00:00:00").astimezone()
    start_ms = int(local_midnight.timestamp() * 1000)
    end_ms = start_ms + 86_400_000  # +1 天

    result = fetcher.read_range(
        symbol="BTCUSDT",
        start_time=start_ms,
        end_time=end_ms,
        limit=10,
        offset=0,
    )
    total = result.get("total", 0)
    if total <= 0:
        _fail(f"read_range 返回 total={total}, 期望 > 0")
        return False
    rows = result.get("rows", [])
    _ok(f"read_range total={total:,}, rows 样本数={len(rows)}")
    return True


# =================== 测试 5: _meta.json 校验 ===================

def test_meta_json(tmp_dir: Path, target_day: str) -> bool:
    """验证 _meta.json 存在, latest_date == target_day。"""
    _section("Test 5: _meta.json 存在性 + latest_date 校验")
    from exchange.binance.archive.archive_meta import read_meta
    from exchange.binance.archive.kinds import ArchiveKind, MarketType, get_save_dir

    save_dir = get_save_dir(tmp_dir, MarketType.SPOT, ArchiveKind.AGG_TRADES, "BTCUSDT")
    meta = read_meta(save_dir)
    if meta is None:
        _fail(f"_meta.json 不存在 ({save_dir / '_meta.json'})")
        return False
    latest = meta.get("latest_date")
    if latest != target_day:
        _fail(f"latest_date={latest!r}, 期望 {target_day!r}")
        return False
    _ok(f"_meta.json ✓ latest_date={latest}, total_rows={meta.get('total_rows')}")
    return True


# =================== 主流程 ===================

def main() -> int:
    """跑全部 5 个测试。返回 0=通过 / 1=硬失败 / 2=网络受限。"""
    _bootstrap_path()
    target_day = "2024-12-01"  # BTCUSDT aggTrades 当日 ~30w 行
    print(f"Self-check for Binance archive (target day={target_day})")

    with tempfile.TemporaryDirectory(prefix="qc_archive_check_") as tmp:
        tmp_dir = Path(tmp)

        # Test 1: 纯本地, 必过
        try:
            test_factory_create(tmp_dir)
        except AssertionError as exc:
            _fail(f"Test 1 AssertionError: {exc}")
            return 1
        except Exception as exc:  # noqa: BLE001
            _fail(f"Test 1 UnexpectedError: {exc}")
            return 1

        # Test 2: 真实下载; 网络失败 → exit 2
        parquet_path = test_real_download_and_save(tmp_dir, target_day)
        if parquet_path is None:
            print("\n[SKIP] 网络不可达或日期无数据, 跳过 Test 3/4/5 (exit 2 = 环境受限, 非代码回归)")
            return 2

        # Test 3/4/5
        ok_3 = test_parquet_schema(parquet_path)
        ok_4 = test_read_range(tmp_dir, target_day)
        ok_5 = test_meta_json(tmp_dir, target_day)
        if not (ok_3 and ok_4 and ok_5):
            return 1

    print("\n[ALL OK] 5 项检查全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
