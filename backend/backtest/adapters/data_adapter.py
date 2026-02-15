"""
trading engine 数据适配器

将内部 K 线数据转换为 trading engine 格式。

主要功能:
    - K 线数据转换为 QuoteTick 列表
    - K 线数据转换为 TradeTick 列表
    - 创建 trading engine Instrument 对象
    - 时间戳和价格精度处理

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

from typing import List, Optional
from decimal import Decimal
from datetime import datetime

import pandas as pd
from loguru import logger

from nautilus_trader.model.data import QuoteTick, TradeTick
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.enums import CurrencyType


# 常用交易对配置
COMMON_PAIRS = {
    "BTCUSDT": {"base": "BTC", "quote": "USDT", "price_precision": 2, "size_precision": 6},
    "ETHUSDT": {"base": "ETH", "quote": "USDT", "price_precision": 2, "size_precision": 5},
    "BNBUSDT": {"base": "BNB", "quote": "USDT", "price_precision": 2, "size_precision": 4},
    "SOLUSDT": {"base": "SOL", "quote": "USDT", "price_precision": 3, "size_precision": 3},
    "ADAUSDT": {"base": "ADA", "quote": "USDT", "price_precision": 5, "size_precision": 1},
    "XRPUSDT": {"base": "XRP", "quote": "USDT", "price_precision": 5, "size_precision": 1},
    "DOTUSDT": {"base": "DOT", "quote": "USDT", "price_precision": 3, "size_precision": 3},
    "DOGEUSDT": {"base": "DOGE", "quote": "USDT", "price_precision": 6, "size_precision": 0},
}


def _ms_to_ns(timestamp_ms: int) -> int:
    """
    将毫秒时间戳转换为纳秒时间戳

    :param timestamp_ms: 毫秒时间戳
    :return: 纳秒时间戳
    """
    return int(timestamp_ms) * 1_000_000


def _validate_kline_df(df: pd.DataFrame) -> None:
    """
    验证 K 线数据 DataFrame 格式

    :param df: K 线数据 DataFrame
    :raises ValueError: 数据格式无效时抛出
    """
    required_columns = ["open", "high", "low", "close", "volume"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(f"K 线数据缺少必要列: {missing_columns}")

    if df.empty:
        raise ValueError("K 线数据为空")

    # 检查是否包含无效值
    if df[required_columns].isnull().any().any():
        null_counts = df[required_columns].isnull().sum()
        raise ValueError(f"K 线数据包含空值: {null_counts[null_counts > 0].to_dict()}")


def _get_timestamp_ns(row: pd.Series, df: pd.DataFrame) -> int:
    """
    从 DataFrame 行中获取纳秒时间戳

    :param row: DataFrame 行
    :param df: 原始 DataFrame（用于获取索引）
    :return: 纳秒时间戳
    """
    # 优先使用 timestamp 列
    if "timestamp" in row:
        ts = row["timestamp"]
        # 根据时间戳长度判断单位
        if ts > 1e18:  # 纳秒
            return int(ts)
        elif ts > 1e12:  # 毫秒
            return _ms_to_ns(ts)
        else:  # 秒
            return int(ts) * 1_000_000_000

    # 使用索引
    idx = row.name
    if isinstance(idx, pd.Timestamp):
        return int(idx.value)  # pandas Timestamp 的 value 已经是纳秒
    elif isinstance(idx, (int, float)):
        if idx > 1e18:
            return int(idx)
        elif idx > 1e12:
            return _ms_to_ns(idx)
        else:
            return int(idx) * 1_000_000_000

    # 默认使用当前时间
    return int(datetime.now().timestamp() * 1_000_000_000)


def kline_to_quote_ticks(
    df: pd.DataFrame,
    instrument: CurrencyPair,
    bid_offset: float = 0.0,
    ask_offset: float = 0.0,
) -> List[QuoteTick]:
    """
    将 K 线 DataFrame 转换为 QuoteTick 列表

    使用 K 线的 close 价格作为基准，生成买卖报价。
    对于加密货币，通常使用 close 价格作为中间价，
    然后根据偏移量生成 bid 和 ask。

    :param df: K 线数据 DataFrame，需要包含 open, high, low, close, volume 列
    :param instrument: trading engine Instrument 对象
    :param bid_offset: 买价偏移量（从 close 价格减去）
    :param ask_offset: 卖价偏移量（从 close 价格加上）
    :return: QuoteTick 列表
    :raises ValueError: 数据格式无效时抛出

    示例:
        >>> df = pd.DataFrame({
        ...     "open": [50000, 51000],
        ...     "high": [52000, 53000],
        ...     "low": [49000, 50000],
        ...     "close": [51000, 52000],
        ...     "volume": [100, 200]
        ... }, index=pd.date_range("2024-01-01", periods=2, freq="1h"))
        >>> instrument = create_instrument("BTCUSDT")
        >>> ticks = kline_to_quote_ticks(df, instrument)
    """
    _validate_kline_df(df)

    ticks = []
    price_precision = instrument.price_precision
    size_precision = instrument.size_precision

    for idx, row in df.iterrows():
        try:
            # 获取时间戳（纳秒）
            ts_ns = _get_timestamp_ns(row, df)

            # 计算买卖价格
            close_price = float(row["close"])
            bid_price = close_price - bid_offset
            ask_price = close_price + ask_offset

            # 使用 volume 作为买卖量（简化处理）
            volume = float(row["volume"])
            bid_size = volume / 2
            ask_size = volume / 2

            # 创建 QuoteTick
            tick = QuoteTick(
                instrument_id=instrument.id,
                bid_price=Price(bid_price, price_precision),
                ask_price=Price(ask_price, price_precision),
                bid_size=Quantity(bid_size, size_precision),
                ask_size=Quantity(ask_size, size_precision),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
            ticks.append(tick)

        except Exception as e:
            logger.warning(f"转换第 {idx} 行 K 线数据失败: {e}")
            continue

    logger.info(f"成功转换 {len(ticks)} 个 QuoteTick")
    return ticks


def kline_to_trade_ticks(
    df: pd.DataFrame,
    instrument: CurrencyPair,
    trade_side: str = "BUY",
) -> List[TradeTick]:
    """
    将 K 线 DataFrame 转换为 TradeTick 列表

    使用 K 线的 close 价格作为成交价，volume 作为成交量。
    注意：这是简化处理，实际交易数据应该包含真实的成交方向和价格。

    :param df: K 线数据 DataFrame，需要包含 open, high, low, close, volume 列
    :param instrument: trading engine Instrument 对象
    :param trade_side: 交易方向，"BUY" 或 "SELL"
    :return: TradeTick 列表
    :raises ValueError: 数据格式无效时抛出

    示例:
        >>> df = pd.DataFrame({
        ...     "open": [50000, 51000],
        ...     "high": [52000, 53000],
        ...     "low": [49000, 50000],
        ...     "close": [51000, 52000],
        ...     "volume": [100, 200]
        ... }, index=pd.date_range("2024-01-01", periods=2, freq="1h"))
        >>> instrument = create_instrument("BTCUSDT")
        >>> ticks = kline_to_trade_ticks(df, instrument, trade_side="BUY")
    """
    _validate_kline_df(df)

    from nautilus_trader.model.enums import AggressorSide

    ticks = []
    price_precision = instrument.price_precision
    size_precision = instrument.size_precision

    # 解析交易方向
    if trade_side.upper() == "BUY":
        aggressor_side = AggressorSide.BUYER
    else:
        aggressor_side = AggressorSide.SELLER

    for idx, row in df.iterrows():
        try:
            # 获取时间戳（纳秒）
            ts_ns = _get_timestamp_ns(row, df)

            # 使用 close 作为成交价
            trade_price = float(row["close"])
            trade_size = float(row["volume"])

            # 创建 TradeTick
            tick = TradeTick(
                instrument_id=instrument.id,
                price=Price(trade_price, price_precision),
                size=Quantity(trade_size, size_precision),
                aggressor_side=aggressor_side,
                trade_id=str(idx),  # 使用索引作为交易 ID
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
            ticks.append(tick)

        except Exception as e:
            logger.warning(f"转换第 {idx} 行 K 线数据失败: {e}")
            continue

    logger.info(f"成功转换 {len(ticks)} 个 TradeTick")
    return ticks


def create_instrument(
    symbol: str,
    venue: str = "BINANCE",
    price_precision: Optional[int] = None,
    size_precision: Optional[int] = None,
) -> CurrencyPair:
    """
    创建 trading engine CurrencyPair Instrument 对象

    支持常见交易对如 BTCUSDT, ETHUSDT 等。
    对于已知交易对，会自动使用预设的精度配置。

    :param symbol: 交易对符号，如 "BTCUSDT"
    :param venue: 交易所名称，默认为 "BINANCE"
    :param price_precision: 价格精度（小数位数），None 则使用预设值
    :param size_precision: 数量精度（小数位数），None 则使用预设值
    :return: CurrencyPair Instrument 对象
    :raises ValueError: 交易对格式无效时抛出

    示例:
        >>> # 创建 BTCUSDT 交易对
        >>> instrument = create_instrument("BTCUSDT")
        >>> print(instrument.id)
        BTCUSDT.BINANCE

        >>> # 创建自定义精度的 ETHUSDT
        >>> instrument = create_instrument("ETHUSDT", price_precision=3, size_precision=4)
    """
    # 标准化符号
    symbol_upper = symbol.upper()

    # 尝试从配置中查找
    config = COMMON_PAIRS.get(symbol_upper)

    if config:
        base_code = config["base"]
        quote_code = config["quote"]
        default_price_precision = config["price_precision"]
        default_size_precision = config["size_precision"]
    else:
        # 尝试解析符号（假设格式为 BASEQUOTE，如 BTCUSDT）
        # 默认使用 USDT 作为 quote
        if "USDT" in symbol_upper:
            base_code = symbol_upper.replace("USDT", "")
            quote_code = "USDT"
        elif "USD" in symbol_upper:
            base_code = symbol_upper.replace("USD", "")
            quote_code = "USD"
        elif "BTC" in symbol_upper and not symbol_upper.startswith("BTC"):
            base_code = symbol_upper.replace("BTC", "")
            quote_code = "BTC"
        elif "ETH" in symbol_upper and not symbol_upper.startswith("ETH"):
            base_code = symbol_upper.replace("ETH", "")
            quote_code = "ETH"
        else:
            # 无法解析，使用整个符号作为 base，USDT 作为 quote
            base_code = symbol_upper
            quote_code = "USDT"

        default_price_precision = 2
        default_size_precision = 6

        logger.warning(f"未找到 {symbol} 的预设配置，使用默认值: base={base_code}, quote={quote_code}")

    # 使用传入的精度或默认值
    final_price_precision = price_precision if price_precision is not None else default_price_precision
    final_size_precision = size_precision if size_precision is not None else default_size_precision

    # 创建货币对象
    base_currency = Currency(
        code=base_code,
        name=base_code,
        currency_type=CurrencyType.CRYPTO,
        precision=final_size_precision,
        iso4217=0,  # 加密货币没有 ISO4217 代码
    )

    quote_currency = Currency(
        code=quote_code,
        name=quote_code,
        currency_type=CurrencyType.CRYPTO if quote_code in ["USDT", "USDC", "BUSD"] else CurrencyType.FIAT,
        precision=final_price_precision,
        iso4217=0,
    )

    # 创建 InstrumentId
    instrument_id = InstrumentId(
        symbol=Symbol(symbol_upper),
        venue=Venue(venue),
    )

    # 创建 CurrencyPair
    instrument = CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol(symbol_upper),
        base_currency=base_currency,
        quote_currency=quote_currency,
        price_precision=final_price_precision,
        size_precision=final_size_precision,
        price_increment=Price(1 / (10 ** final_price_precision), final_price_precision),
        size_increment=Quantity(1 / (10 ** final_size_precision), final_size_precision),
        lot_size=None,
        max_quantity=None,
        min_quantity=None,
        max_notional=None,
        min_notional=None,
        max_price=None,
        min_price=None,
        margin_init=Decimal("1.0"),
        margin_maint=Decimal("1.0"),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=0,
        ts_init=0,
    )

    logger.info(f"创建 Instrument: {instrument_id}, 价格精度: {final_price_precision}, 数量精度: {final_size_precision}")
    return instrument


def register_custom_pair(
    symbol: str,
    base: str,
    quote: str,
    price_precision: int,
    size_precision: int,
) -> None:
    """
    注册自定义交易对配置

    :param symbol: 交易对符号
    :param base: 基础货币代码
    :param quote: 计价货币代码
    :param price_precision: 价格精度
    :param size_precision: 数量精度

    示例:
        >>> register_custom_pair("PEPEUSDT", "PEPE", "USDT", 10, 0)
        >>> instrument = create_instrument("PEPEUSDT")
    """
    COMMON_PAIRS[symbol.upper()] = {
        "base": base.upper(),
        "quote": quote.upper(),
        "price_precision": price_precision,
        "size_precision": size_precision,
    }
    logger.info(f"注册自定义交易对: {symbol}")
