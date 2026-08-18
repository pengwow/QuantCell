"""StrategyContext 多数据源特征支持测试。"""

import pandas as pd

from strategy.base import StrategyContext


class TestStrategyContext:
    def test_default_values(self):
        ctx = StrategyContext(symbol="BTCUSDT")
        assert ctx.features == {}
        assert ctx.feature_dataframe is None
        assert ctx.data_type == "kline"

    def test_get_feature(self):
        ctx = StrategyContext(
            symbol="BTCUSDT",
            features={"funding_rate": 0.0001},
        )
        assert ctx.get_feature("funding_rate") == 0.0001

    def test_get_feature_default(self):
        ctx = StrategyContext(symbol="BTCUSDT")
        assert ctx.get_feature("nonexistent", -1.0) == -1.0

    def test_has_feature(self):
        ctx = StrategyContext(
            symbol="BTCUSDT",
            features={"funding_rate": 0.0001},
        )
        assert ctx.has_feature("funding_rate") is True
        assert ctx.has_feature("nonexistent") is False

    def test_with_feature_dataframe(self):
        df = pd.DataFrame(
            {
                "feature_funding_rate": [0.0001, -0.0002],
                "feature_open_interest": [1000.0, 1200.0],
            }
        )
        ctx = StrategyContext(
            symbol="BTCUSDT",
            feature_dataframe=df,
            data_type="fundingRate",
        )
        assert ctx.data_type == "fundingRate"
        assert len(ctx.feature_dataframe) == 2
