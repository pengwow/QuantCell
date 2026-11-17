"""价格列禁 Float 门禁（命名审计 P2-6 价格域，P2-7 收紧为全禁）。

价格落库 Float 有二进制精度丢失风险（0.1+0.2 类问题在成交/持仓表上不可接受）。
P2-7 已把 worker 域 6 个价格列迁移 DECIMAL(30, 8)（PriceAsFloat 收口 float 读出），
基线清空为全禁：任何 Float 价格列（含 K线 OHLC / ticker / 未来新表）立即变红。

价格语义列判定：列名小写后含 "price"，或精确命中 K线 OHLC 四列名
（open/high/low/close）。数量（quantity）/盈亏（pnl）/费用（fee）属资金数量域，
不是价格，不在本档（后续档位再收）。

P2-11 补充：K线三表 OHLC 四列额外禁 String（已迁移 DECIMAL(40, 8)，
作为「价格字符串列」的最后收口——字符串价格同样绕开数值语义）。
"""

from sqlalchemy import Float, Numeric, String

from collector.db.database import Base, _import_all_models

# 已知存量 Float 价格列 —— P2-7 迁移完成后清空（保留空集断言，新增价格列必走 DECIMAL）
KNOWN_FLOAT_PRICE_COLUMNS: frozenset = frozenset()

_PRICE_EXACT_NAMES = {"open", "high", "low", "close"}

# P2-11 后 OHLC 必须落在 K线三表且为 DECIMAL
KLINE_TABLES = ("crypto_spot_klines", "crypto_future_klines", "stock_klines")


def _is_price_column(name: str) -> bool:
    lowered = (name or "").lower()
    return "price" in lowered or lowered in _PRICE_EXACT_NAMES


def assert_price_columns_no_float() -> None:
    _import_all_models()
    found = set()
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if _is_price_column(col.name) and isinstance(col.type, Float):
                found.add((table.name, col.name))
    assert found == KNOWN_FLOAT_PRICE_COLUMNS, (
        "Float 价格列与基线不一致。\n"
        f"  基线外新增（须改 DECIMAL/String）: {sorted(found - KNOWN_FLOAT_PRICE_COLUMNS)}\n"
        f"  基线内已迁移（从基线删除收紧）: {sorted(KNOWN_FLOAT_PRICE_COLUMNS - found)}"
    )


def test_float_price_columns_match_baseline() -> None:
    assert_price_columns_no_float()


def test_kline_ohlc_columns_are_decimal() -> None:
    """K线三表 OHLC 四列必须存在且为 NUMERIC 家族（禁 String/Float 回退）。"""
    _import_all_models()
    for table_name in KLINE_TABLES:
        table = Base.metadata.tables.get(table_name)
        assert table is not None, f"K线表 {table_name} 未在 metadata 注册"
        for col_name in ("open", "high", "low", "close"):
            col = table.columns.get(col_name)
            assert col is not None, f"{table_name}.{col_name} 缺失"
            assert isinstance(col.type, Numeric), (
                f"{table_name}.{col_name} 应为 DECIMAL/NUMERIC，实际 {col.type!r}（String/Float 价格列是被禁止的历史形态）"
            )
            assert not isinstance(col.type, String)
