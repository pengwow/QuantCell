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
