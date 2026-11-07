"""DownloadCryptoRequest 校验矩阵测试。

覆盖 data_type × market 组合合法性、K 线类 interval 必填、非法枚举拒绝。
契约与前端 types/data.ts 的 FUTURES_ONLY_KINDS（5 种期货专属类型）对齐：
期货专属类型在 spot 市场必须被拒绝（Binance 无此数据）。
"""

import pytest
from pydantic import ValidationError

from collector.schemas.data import VALID_DATA_TYPES, DownloadCryptoRequest

# 期货专属类型：仅 um/cm 市场有该数据
FUTURES_ONLY = ["markPriceKlines", "indexPriceKlines", "premiumIndexKlines", "fundingRate", "openInterest"]
# K 线类（interval 必填）
KLINE_TYPES = ["kline", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"]


def make_req(**overrides):
    base: dict = {"symbols": ["BTCUSDT"], "start": "2025-01-01", "end": "2025-01-02"}
    base.update(overrides)
    return base


class TestDataTypeMarketMatrix:
    @pytest.mark.parametrize("market", ["um", "cm"])
    @pytest.mark.parametrize("data_type", FUTURES_ONLY)
    def test_futures_only_types_accepted_on_um_cm(self, data_type: str, market: str):
        interval = ["15m"] if data_type in KLINE_TYPES else []
        req = DownloadCryptoRequest(**make_req(data_type=data_type, market=market, interval=interval))
        assert req.market == market

    @pytest.mark.parametrize("data_type", FUTURES_ONLY)
    def test_futures_only_types_reject_spot(self, data_type: str):
        interval = ["15m"] if data_type in KLINE_TYPES else []
        with pytest.raises(ValidationError, match="仅支持 market=um 或 cm"):
            DownloadCryptoRequest(**make_req(data_type=data_type, market="spot", interval=interval))

    @pytest.mark.parametrize("data_type", ["kline", "aggTrades", "trades", "bookDepth", "bookTicker"])
    @pytest.mark.parametrize("market", ["spot", "um", "cm"])
    def test_common_types_accepted_on_all_markets(self, data_type: str, market: str):
        interval = ["15m"] if data_type == "kline" else []
        req = DownloadCryptoRequest(**make_req(data_type=data_type, market=market, interval=interval))
        assert req.market == market


class TestIntervalRequired:
    @pytest.mark.parametrize("data_type", KLINE_TYPES)
    def test_kline_types_require_interval(self, data_type: str):
        # 期货专属 K 线类用 um 市场触发，避免先被 market=spot 校验拦截
        market = "spot" if data_type == "kline" else "um"
        with pytest.raises(ValidationError, match="必须指定 interval"):
            DownloadCryptoRequest(**make_req(data_type=data_type, market=market, interval=[]))

    @pytest.mark.parametrize(
        "data_type", ["aggTrades", "trades", "bookDepth", "bookTicker", "fundingRate", "openInterest"]
    )
    def test_non_kline_types_allow_empty_interval(self, data_type: str):
        market = "um" if data_type in ("fundingRate", "openInterest") else "spot"
        req = DownloadCryptoRequest(**make_req(data_type=data_type, market=market, interval=[]))
        assert req.interval == []


class TestInvalidEnums:
    def test_empty_symbols_rejected(self):
        # 空品种列表会创建空跑任务，必须在入口拒绝
        with pytest.raises(ValidationError, match="symbols 不能为空"):
            DownloadCryptoRequest(**make_req(data_type="kline", market="spot", symbols=[], interval=["15m"]))

    def test_invalid_data_type_rejected(self):
        with pytest.raises(ValidationError, match="无效的 data_type"):
            DownloadCryptoRequest(**make_req(data_type="oops"))

    def test_invalid_market_rejected(self):
        with pytest.raises(ValidationError, match="无效的 market"):
            DownloadCryptoRequest(**make_req(data_type="kline", market="futures"))

    def test_valid_data_types_cover_all_10(self):
        # 10 种数据类型：1 个 K线 + 4 个归档 + 2 个衍生 + 3 个特殊 K线
        assert len(VALID_DATA_TYPES) == 10
