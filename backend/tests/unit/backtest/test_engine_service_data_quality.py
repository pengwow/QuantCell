"""EventDrivenBacktestService 数据质量测试。

覆盖 P1 数据质量缺口(D2 / 4.3 建议):
- _parse_symbol 解析(短符号 / 分隔符 / 嵌套 tuple 修复)
- NaN / Inf 清洗,不产出 NaN 指标
- 乱序时间戳排序、重复时间戳去重
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
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


def _build_df(timestamps=None, **overrides) -> pd.DataFrame:
    """构造标准 OHLCV 时钟序列 DataFrame。"""
    if timestamps is None:
        timestamps = pd.date_range("2025-01-01", periods=4, freq="1h")
    base = {
        "timestamp": timestamps,
        "open": [100.0, 101.0, 102.0, 103.0],
        "high": [105.0, 106.0, 107.0, 108.0],
        "low": [99.0, 100.0, 101.0, 102.0],
        "close": [103.0, 104.0, 105.0, 106.0],
        "volume": [1000.0, 2000.0, 3000.0, 4000.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _make_service_and_engine():
    """构造 service + fake engine,fake 在调用期快照 parquet 内容,避免临时文件被回收。"""
    service = EventDrivenBacktestService(data_provider=MagicMock())
    engine = MagicMock()
    engine.loaded_dfs: list[pd.DataFrame] = []

    def _fake_load(path, instrument):
        df = pd.read_parquet(path)
        engine.loaded_dfs.append(df)
        return df

    engine.load_data_from_parquet.side_effect = _fake_load
    return service, engine


def _run_load(service, engine, df):
    """执行 _load_data_to_engine 并返回引擎实际接收的 parquet 数据。"""
    service._load_data_to_engine(
        engine=engine,
        data_dict={"BTCUSDT_1h": df},
        symbols=["BTCUSDT"],
        timeframes=["1h"],
        base_currency="USDT",
        leverage=1.0,
        init_cash=100000.0,
    )
    return engine.loaded_dfs[-1]


class TestLoadDataQuality:
    def test_clean_data_passthrough(self):
        service, engine = _make_service_and_engine()
        parsed_df = _run_load(service, engine, _build_df())
        assert len(parsed_df) == 4
        assert parsed_df["close"].tolist() == [103.0, 104.0, 105.0, 106.0]

    def test_nan_filled_with_zero(self):
        service, engine = _make_service_and_engine()
        df = _build_df(open=[np.nan, 101.0, 102.0, 103.0])
        parsed_df = _run_load(service, engine, df)
        assert parsed_df["open"].iloc[0] == 0.0

    def test_inf_filled_as_nan_then_zero(self):
        """Inf 必须被清洗(转 NaN 后填 0),否则 Inf/Inf 会产出 NaN 指标"""
        service, engine = _make_service_and_engine()
        df = _build_df(high=[105.0, np.inf, 107.0, 108.0])
        parsed_df = _run_load(service, engine, df)
        assert np.isfinite(parsed_df["high"]).all()
        assert parsed_df["high"].iloc[1] == 0.0

    def test_out_of_order_timestamps_sorted(self):
        """乱序 bar:排序为递增,避免事件驱动回测失真"""
        service, engine = _make_service_and_engine()
        df = _build_df(
            timestamps=[
                "2025-01-01 03:00:00",
                "2025-01-01 01:00:00",
                "2025-01-01 02:00:00",
                "2025-01-01 00:00:00",
            ]
        )
        parsed_df = _run_load(service, engine, df)
        assert parsed_df.index.is_monotonic_increasing

    def test_duplicated_timestamps_deduplicated(self):
        """同一 timestamp 多条 bar:保留最后一条,避免重复计"""
        service, engine = _make_service_and_engine()
        df = _build_df(
            timestamps=[
                "2025-01-01 00:00:00",
                "2025-01-01 00:00:00",
                "2025-01-01 01:00:00",
                "2025-01-01 02:00:00",
            ],
            open=[100.0, 101.0, 102.0, 103.0],
        )
        parsed_df = _run_load(service, engine, df)
        assert len(parsed_df) == 3
        assert parsed_df["open"].iloc[0] == 101.0
