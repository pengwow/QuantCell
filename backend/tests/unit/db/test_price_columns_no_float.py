"""价格列禁 Float 门禁（命名审计 P2-6 价格域）。

价格落库 Float 有二进制精度丢失风险（0.1+0.2 类问题在成交/持仓表上不可接受）。
现状：K线 OHLC 四列已是 String（volume 档位定档），ticker 行情是 DECIMAL(30,8)；
仅 worker 域历史订单/成交/持仓表还是 Float —— 收进 KNOWN_FLOAT_PRICE_COLUMNS
基线做集合相等断言：新出现 Float 价格列立即变红；迁移 DECIMAL 时同步从基线删除收紧。

价格语义列判定：列名小写后含 "price"，或精确命中 K线 OHLC 四列名
（open/high/low/close）。数量（quantity）/盈亏（pnl）/费用（fee）属资金数量域，
不是价格，不在本档（后续档位再收）。
"""

from sqlalchemy import Float

from collector.db.database import Base, _import_all_models

# 已知存量 Float 价格列（表名, 列名）—— 迁移 DECIMAL 后从此集合删除即收紧
KNOWN_FLOAT_PRICE_COLUMNS = frozenset(
    {
        ("worker_trades", "price"),
        ("worker_orders", "price"),
        ("worker_orders", "avg_fill_price"),
        ("worker_positions", "entry_price"),
        ("worker_positions", "current_price"),
        ("worker_fill_evidence", "price"),
    }
)

_PRICE_EXACT_NAMES = {"open", "high", "low", "close"}


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
