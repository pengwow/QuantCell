"""
trading engine 数据适配器

将内部 K 线数据转换为 trading engine 格式。

主要功能:
    - K 线数据转换为 QuoteTick 列表
    - K 线数据转换为 TradeTick 列表
    - K 线数据转换为 Bar 对象列表
    - 从 CSV/Parquet 文件加载 Bar 数据
    - 创建 trading engine Instrument 对象
    - 时间戳和价格精度处理

作者: QuantCell Team
版本: 1.1.0
日期: 2026-02-23
"""

from typing import List, Optional, Dict, Callable
from decimal import Decimal
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

from nautilus_trader.model.data import QuoteTick, TradeTick, Bar
from nautilus_trader.model.data import BarType, BarSpecification
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, TradeId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.enums import CurrencyType, BarAggregation, PriceType
from nautilus_trader.persistence.wranglers import BarDataWrangler


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
    null_check = df[required_columns].isnull()
    if null_check.any().any():
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
        ts = float(row["timestamp"])
        # 根据时间戳长度判断单位
        if ts > 1e18:  # 纳秒
            return int(ts)
        elif ts > 1e12:  # 毫秒
            return _ms_to_ns(int(ts))
        else:  # 秒
            return int(ts) * 1_000_000_000

    # 使用索引
    idx = row.name
    if isinstance(idx, pd.Timestamp):
        return int(idx.value)  # pandas Timestamp 的 value 已经是纳秒
    elif isinstance(idx, (int, float)):
        idx_float = float(idx)
        if idx_float > 1e18:
            return int(idx_float)
        elif idx_float > 1e12:
            return _ms_to_ns(int(idx_float))
        else:
            return int(idx_float) * 1_000_000_000

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
                trade_id=TradeId(str(idx)),  # 使用索引作为交易 ID
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


def _create_bar_type(
    instrument: CurrencyPair,
    aggregation: BarAggregation,
    step: int,
    price_type: PriceType = PriceType.LAST,
) -> BarType:
    """
    创建 BarType 对象

    :param instrument: 交易品种对象
    :param aggregation: K线聚合类型（如 MINUTE, HOUR, DAY）
    :param step: 时间步长
    :param price_type: 价格类型，默认为 LAST
    :return: BarType 对象
    """
    bar_spec = BarSpecification(aggregation, price_type, step)
    return BarType(instrument.id, bar_spec)


def _standardize_dataframe(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    timestamp_column: str = "timestamp",
) -> pd.DataFrame:
    """
    标准化 DataFrame 格式为 BarDataWrangler 所需的结构

    标准格式要求：
    - 索引：timestamp（纳秒时间戳）
    - 列：open, high, low, close, volume（volume 可选）

    :param df: 原始 DataFrame
    :param column_mapping: 列名映射字典，如 {"open_price": "open", "vol": "volume"}
    :param timestamp_column: 时间戳列名
    :return: 标准化后的 DataFrame
    :raises ValueError: 数据格式无效时抛出
    """
    df = df.copy()

    # 应用列名映射
    if column_mapping:
        df = df.rename(columns=column_mapping)

    # 检查必要列
    required_columns = ["open", "high", "low", "close"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"缺少必要列: {missing_columns}，当前列: {list(df.columns)}")

    # 处理时间戳列
    if timestamp_column in df.columns:
        # 转换时间戳列为 datetime 类型
        if not pd.api.types.is_datetime64_any_dtype(df[timestamp_column]):
            df[timestamp_column] = pd.to_datetime(df[timestamp_column], unit="ms")
        # 设置为索引
        df = df.set_index(timestamp_column)
    elif not isinstance(df.index, pd.DatetimeIndex):
        # 尝试将索引转换为 datetime
        try:
            df.index = pd.to_datetime(df.index, unit="ms")
        except (ValueError, TypeError):
            raise ValueError("无法识别时间戳列，请确保有 timestamp 列或 DatetimeIndex 索引")

    # 确保索引名称为 timestamp（BarDataWrangler 要求）
    df.index.name = "timestamp"

    # 确保 volume 列存在（可选）
    if "volume" not in df.columns:
        df["volume"] = 0.0
        logger.warning("DataFrame 缺少 volume 列，使用默认值 0")

    # 只保留需要的列
    columns_to_keep = ["open", "high", "low", "close", "volume"]
    available_cols = [col for col in columns_to_keep if col in df.columns]
    df = df[available_cols].copy()

    # 数据类型转换
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 检查空值
    has_null = bool(df[required_columns].isnull().any().any())
    if has_null:
        null_counts = df[required_columns].isnull().sum()
        raise ValueError(f"数据包含空值: {null_counts[null_counts > 0].to_dict()}")

    # 检查数据逻辑
    invalid_high_low = (df["high"] < df["low"]).any()
    if invalid_high_low:
        raise ValueError("数据中存在 high < low 的无效数据")

    invalid_ohlc = (
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    ).any()
    if invalid_ohlc:
        logger.warning("数据中存在 OHLC 逻辑不一致的情况（high 不是最高或 low 不是最低）")

    return df


def kline_to_bars(
    df: pd.DataFrame,
    instrument: CurrencyPair,
    aggregation: BarAggregation = BarAggregation.MINUTE,
    step: int = 1,
    price_type: PriceType = PriceType.LAST,
    column_mapping: Optional[Dict[str, str]] = None,
    timestamp_column: str = "timestamp",
) -> List[Bar]:
    """
    将 K 线 DataFrame 转换为 NautilusTrader Bar 对象列表

    这是 Bar 数据转换的核心函数，使用 BarDataWrangler 将 DataFrame 转换为 Bar 对象。

    :param df: K 线数据 DataFrame，需要包含 open, high, low, close, volume 列
    :param instrument: trading engine Instrument 对象
    :param aggregation: K线聚合类型，默认为 MINUTE
    :param step: 时间步长，如 1 表示 1 分钟，5 表示 5 分钟
    :param price_type: 价格类型，默认为 LAST
    :param column_mapping: 列名映射字典，用于处理不同列名格式
    :param timestamp_column: 时间戳列名，默认为 "timestamp"
    :return: Bar 对象列表
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
        >>> bars = kline_to_bars(df, instrument, aggregation=BarAggregation.HOUR, step=1)

        >>> # 使用自定义列名映射
        >>> df_custom = pd.DataFrame({
        ...     "open_price": [50000, 51000],
        ...     "high_price": [52000, 53000],
        ...     "low_price": [49000, 50000],
        ...     "close_price": [51000, 52000],
        ...     "vol": [100, 200]
        ... })
        >>> mapping = {"open_price": "open", "high_price": "high", "low_price": "low",
        ...            "close_price": "close", "vol": "volume"}
        >>> bars = kline_to_bars(df_custom, instrument, column_mapping=mapping)
    """
    if df.empty:
        raise ValueError("输入的 DataFrame 为空")

    try:
        # 标准化 DataFrame
        df_standardized = _standardize_dataframe(df, column_mapping, timestamp_column)

        # 创建 BarType
        bar_type = _create_bar_type(instrument, aggregation, step, price_type)

        # 使用 BarDataWrangler 转换数据
        wrangler = BarDataWrangler(bar_type, instrument)
        bars: List[Bar] = wrangler.process(df_standardized)

        logger.info(
            f"成功转换 {len(bars)} 个 Bar 对象，"
            f"品种: {instrument.id}, 周期: {aggregation.name}-{step}, "
            f"时间范围: {df_standardized.index[0]} ~ {df_standardized.index[-1]}"
        )
        return bars

    except Exception as e:
        logger.error(f"K 线数据转换为 Bar 对象失败: {e}")
        raise


def load_bars_from_csv(
    file_path: str | Path,
    instrument: CurrencyPair,
    aggregation: BarAggregation = BarAggregation.MINUTE,
    step: int = 1,
    price_type: PriceType = PriceType.LAST,
    sep: str = ",",
    header: int = 0,
    timestamp_column: str = "timestamp",
    column_mapping: Optional[Dict[str, str]] = None,
    **pandas_kwargs,
) -> List[Bar]:
    """
    从 CSV 文件加载 Bar 数据

    支持常见 CSV 格式，包括带/不带 header，不同分隔符，不同列名等。

    :param file_path: CSV 文件路径
    :param instrument: trading engine Instrument 对象
    :param aggregation: K线聚合类型，默认为 MINUTE
    :param step: 时间步长
    :param price_type: 价格类型，默认为 LAST
    :param sep: CSV 分隔符，默认为逗号
    :param header: header 行号，None 表示无 header，默认为 0
    :param timestamp_column: 时间戳列名
    :param column_mapping: 列名映射字典
    :param pandas_kwargs: 传递给 pd.read_csv 的其他参数
    :return: Bar 对象列表
    :raises FileNotFoundError: 文件不存在时抛出
    :raises ValueError: 数据格式无效时抛出

    示例:
        >>> # 加载标准格式的 CSV
        >>> instrument = create_instrument("BTCUSDT")
        >>> bars = load_bars_from_csv("data/btc_1min.csv", instrument)

        >>> # 加载分号分隔的 CSV
        >>> bars = load_bars_from_csv(
        ...     "data/eurusd.csv",
        ...     instrument,
        ...     sep=";",
        ...     decimal="."
        ... )

        >>> # 加载无 header 的 CSV，指定列名
        >>> bars = load_bars_from_csv(
        ...     "data/raw.csv",
        ...     instrument,
        ...     header=None,
        ...     names=["timestamp", "open", "high", "low", "close", "volume"]
        ... )

        >>> # 使用列名映射加载非标准格式 CSV
        >>> bars = load_bars_from_csv(
        ...     "data/custom.csv",
        ...     instrument,
        ...     column_mapping={
        ...         "Open": "open",
        ...         "High": "high",
        ...         "Low": "low",
        ...         "Close": "close",
        ...         "Volume": "volume",
        ...         "Time": "timestamp"
        ...     },
        ...     timestamp_column="Time"
        ... )
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {file_path}")

    try:
        # 读取 CSV 文件
        df = pd.read_csv(
            file_path,
            sep=sep,
            header=header,
            **pandas_kwargs
        )

        logger.info(f"成功读取 CSV 文件: {file_path}，共 {len(df)} 行")

        # 转换为 Bar 对象
        bars = kline_to_bars(
            df=df,
            instrument=instrument,
            aggregation=aggregation,
            step=step,
            price_type=price_type,
            column_mapping=column_mapping,
            timestamp_column=timestamp_column,
        )

        return bars

    except Exception as e:
        logger.error(f"从 CSV 加载 Bar 数据失败: {e}")
        raise


def load_bars_from_parquet(
    file_path: str | Path,
    instrument: CurrencyPair,
    aggregation: BarAggregation = BarAggregation.MINUTE,
    step: int = 1,
    price_type: PriceType = PriceType.LAST,
    timestamp_column: str = "timestamp",
    column_mapping: Optional[Dict[str, str]] = None,
    columns: Optional[List[str]] = None,
    **pandas_kwargs,
) -> List[Bar]:
    """
    从 Parquet 文件加载 Bar 数据

    Parquet 格式具有高效的压缩和快速的读写性能，适合存储大量历史数据。

    :param file_path: Parquet 文件路径
    :param instrument: trading engine Instrument 对象
    :param aggregation: K线聚合类型，默认为 MINUTE
    :param step: 时间步长
    :param price_type: 价格类型，默认为 LAST
    :param timestamp_column: 时间戳列名
    :param column_mapping: 列名映射字典
    :param columns: 要读取的列列表，None 表示读取所有列
    :param pandas_kwargs: 传递给 pd.read_parquet 的其他参数
    :return: Bar 对象列表
    :raises FileNotFoundError: 文件不存在时抛出
    :raises ValueError: 数据格式无效时抛出

    示例:
        >>> # 加载标准格式的 Parquet 文件
        >>> instrument = create_instrument("BTCUSDT")
        >>> bars = load_bars_from_parquet("data/btc_1min.parquet", instrument)

        >>> # 只读取特定列
        >>> bars = load_bars_from_parquet(
        ...     "data/large_file.parquet",
        ...     instrument,
        ...     columns=["timestamp", "open", "high", "low", "close", "volume"]
        ... )

        >>> # 使用列名映射
        >>> bars = load_bars_from_parquet(
        ...     "data/custom.parquet",
        ...     instrument,
        ...     column_mapping={
        ...         "open_price": "open",
        ...         "high_price": "high",
        ...         "low_price": "low",
        ...         "close_price": "close",
        ...         "vol": "volume"
        ...     }
        ... )
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Parquet 文件不存在: {file_path}")

    try:
        # 读取 Parquet 文件
        df = pd.read_parquet(
            file_path,
            columns=columns,
            **pandas_kwargs
        )

        logger.info(f"成功读取 Parquet 文件: {file_path}，共 {len(df)} 行")

        # 转换为 Bar 对象
        bars = kline_to_bars(
            df=df,
            instrument=instrument,
            aggregation=aggregation,
            step=step,
            price_type=price_type,
            column_mapping=column_mapping,
            timestamp_column=timestamp_column,
        )

        return bars

    except Exception as e:
        logger.error(f"从 Parquet 加载 Bar 数据失败: {e}")
        raise


def create_bar_type_from_string(
    bar_type_str: str,
) -> BarType:
    """
    从字符串创建 BarType 对象

    字符串格式: SYMBOL.VENUE-STEP-AGGREGATION-PRICE_TYPE-EXTERNAL
    例如: BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL

    :param bar_type_str: BarType 字符串表示
    :return: BarType 对象
    :raises ValueError: 字符串格式无效时抛出

    示例:
        >>> bar_type = create_bar_type_from_string("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")
        >>> print(bar_type)
        BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL
    """
    try:
        return BarType.from_str(bar_type_str)
    except Exception as e:
        raise ValueError(f"无效的 BarType 字符串: {bar_type_str}，错误: {e}")


def get_bar_aggregation_from_string(aggregation_str: str) -> BarAggregation:
    """
    从字符串获取 BarAggregation 枚举值

    支持的值:
    - TICK, SECOND, MINUTE, HOUR, DAY, WEEK, MONTH
    - 不区分大小写

    :param aggregation_str: 聚合类型字符串
    :return: BarAggregation 枚举值
    :raises ValueError: 字符串无效时抛出

    示例:
        >>> agg = get_bar_aggregation_from_string("minute")
        >>> print(agg)
        BarAggregation.MINUTE
    """
    aggregation_map = {
        "tick": BarAggregation.TICK,
        "second": BarAggregation.SECOND,
        "minute": BarAggregation.MINUTE,
        "hour": BarAggregation.HOUR,
        "day": BarAggregation.DAY,
        "week": BarAggregation.WEEK,
        "month": BarAggregation.MONTH,
    }

    aggregation_lower = aggregation_str.lower()
    if aggregation_lower not in aggregation_map:
        raise ValueError(
            f"无效的聚合类型: {aggregation_str}，"
            f"支持的值: {list(aggregation_map.keys())}"
        )

    return aggregation_map[aggregation_lower]
