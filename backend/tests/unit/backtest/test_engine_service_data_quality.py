"""EventDrivenBacktestService._parse_symbol 解析测试。

数据清洗契约（NaN/Inf→0、乱序排序、重复去重）已收敛到 BacktestLoop.clean_ohlcv_df，
对应测试见 test_backtest_loop_clean.py。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backtest.engine_service import EventDrivenBacktestService


class TestParseSymbol:
    """_parse_symbol:多处实现中最易出 bug 的 engine_service 版本。"""

    def setup_method(self):
        self.service = EventDrivenBacktestService(MagicMock())

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("BTCUSDT", ("BTC", "USDT")),
            ("BTC/USDT", ("BTC", "USDT")),
            ("BTC-USDT", ("BTC", "USDT")),
            ("BTC_USDT", ("BTC", "USDT")),
            ("ETHUSDT", ("ETH", "USDT")),
            ("SOLUSDT", ("SOL", "USDT")),
            # 短符号: base 兜底 USDT,quote 不能是嵌套 tuple(历史 bug)
            ("ETH", ("ETH", "USDT")),
            ("btcusdt", ("BTC", "USDT")),
        ],
    )
    def test_parse_symbol_common(self, symbol, expected):
        assert self.service._parse_symbol(symbol) == expected

    def test_parse_symbol_short_symbol_not_nested_tuple(self):
        base, quote = self.service._parse_symbol("ETH")
        assert base == "ETH"
        assert quote == "USDT"
        assert isinstance(quote, str)
