"""方向词汇边界测试：vocab 归一层 + schemas Literal + routes 查询参数 helper。

Task 7/9 结束后 routes helper 与前端类型对齐的验收用例也从这里跑，
保证「词汇边界 = 一个测试文件」。
"""

import pytest
from pydantic import ValidationError

from worker.vocab import normalize_position_side, normalize_side


class TestNormalizeSide:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("buy", "buy"),
            ("BUY", "buy"),
            ("Buy", "buy"),
            (" sell", "sell"),
            ("SELL ", "sell"),
        ],
    )
    def test_case_insensitive(self, raw: str, expected: str) -> None:
        assert normalize_side(raw) == expected

    @pytest.mark.parametrize("raw", ["", " BuySell", "hold", "long", "1"])
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError):
            normalize_side(raw)


class TestNormalizePositionSide:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("long", "long"),
            ("LONG", "long"),
            ("Short", "short"),
            ("both", "both"),
            ("BOTH ", "both"),
        ],
    )
    def test_case_insensitive(self, raw: str, expected: str) -> None:
        assert normalize_position_side(raw) == expected

    @pytest.mark.parametrize("raw", ["", "buy", "NET", "longshort"])
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError):
            normalize_position_side(raw)


class TestSchemaLiteral:
    """schemas 的方向字段必须 Literal 强校验（裸 str 是脏数据的入口之一）。"""

    def test_position_info_accepts_canonical(self) -> None:
        from datetime import datetime

        from worker import schemas

        p = schemas.PositionInfo(
            symbol="BTC/USDT",
            side="long",
            quantity=1.0,
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=1000.0,
            unrealized_pnl_pct=2.0,
            timestamp=datetime(2026, 11, 16),
        )
        assert p.side == "long"

    def test_position_info_rejects_uppercase(self) -> None:
        from datetime import datetime

        from worker import schemas

        with pytest.raises(ValidationError):
            schemas.PositionInfo(
                symbol="BTC/USDT",
                side="LONG",
                quantity=1.0,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=1000.0,
                unrealized_pnl_pct=2.0,
                timestamp=datetime(2026, 11, 16),
            )

    def test_order_info_rejects_uppercase(self) -> None:
        from datetime import datetime

        from worker import schemas

        with pytest.raises(ValidationError):
            schemas.OrderInfo(
                order_id="o1",
                symbol="BTC/USDT",
                side="BUY",
                order_type="market",
                quantity=1.0,
                price=None,
                status="FILLED",
                filled_quantity=0.0,
                created_at=datetime(2026, 11, 16),
            )
