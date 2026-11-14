# 数据处理器
import time
from typing import Any

from utils.logger import LogType, get_logger
from utils.timestamp_utils import normalize_to_nanoseconds

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class DataProcessor:
    """数据处理器，负责处理和标准化从WebSocket接收到的数据"""

    def __init__(self):
        """初始化数据处理器"""
        self.supported_exchanges = {
            "binance",
            # 后续可以添加其他交易所
        }

        self.supported_data_types = {
            "kline",
            "depth",
            "aggTrade",
            "trade",
            "ticker",
            "miniTicker",
            "bookTicker",
        }

        # handler 方法名为小写蛇形，而部分 data_type 是 camelCase，动态拼名会 miss
        # （aggTrade 会拼出不存在的 _process_binance_aggTrade）；显式别名兜住不一致项，
        # 其余 data_type 与方法名后缀一致，保持精确匹配
        self._handler_name_alias = {"aggTrade": "aggtrade"}

    def process_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """
        处理消息

        Args:
            message: 待处理的消息

        Returns:
            Optional[Dict[str, Any]]: 处理后的消息，None表示处理失败
        """
        try:
            # 验证消息基本结构
            if not self._validate_message(message):
                return None

            exchange = message.get("exchange", "")
            data_type = message.get("data_type", "")

            # 根据交易所和数据类型调用相应的处理方法（camelCase 走别名表）
            handler_suffix = self._handler_name_alias.get(data_type, data_type)
            handler = getattr(self, f"_process_{exchange}_{handler_suffix}", None)
            if handler:
                return handler(message)
            else:
                # 使用通用处理方法
                return self._process_generic(message)

        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            return None

    def _validate_message(self, message: dict[str, Any]) -> bool:
        """
        验证消息结构

        Args:
            message: 待验证的消息

        Returns:
            bool: 验证是否通过
        """
        # 检查必要字段
        required_fields = ["exchange", "data_type"]
        for field in required_fields:
            if field not in message:
                logger.warning(f"消息缺少必要字段: {field}, 消息: {message}")
                return False

        # 检查交易所是否支持
        exchange = message["exchange"]
        if exchange not in self.supported_exchanges:
            logger.warning(f"不支持的交易所: {exchange}")
            return False

        # 检查数据类型是否支持
        data_type = message["data_type"]
        if data_type not in self.supported_data_types:
            logger.warning(f"不支持的数据类型: {data_type}")
            return False

        return True

    def _process_generic(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        通用消息处理方法

        Args:
            message: 待处理的消息

        Returns:
            Dict[str, Any]: 处理后的消息
        """
        # 添加处理时间戳 (统一使用纳秒级)
        message["processed_timestamp"] = int(time.time() * 1_000_000_000)

        return message

    def _process_binance_kline(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        处理币安K线数据

        Args:
            message: 待处理的K线消息

        Returns:
            Dict[str, Any]: 处理后的K线数据
        """
        # 调用通用处理方法
        processed = self._process_generic(message)

        # 从币安K线数据中提取字段
        k = processed.get("k", {})
        if not k:
            logger.warning(f"K线数据缺少k字段: {processed}")
            return None

        # 提取并标准化K线数据字段
        # 币安字段: t=open_time, T=close_time, o=open, h=high, l=low, c=close, v=volume
        #           q=quote_volume, n=trades, i=interval, x=is_final
        #           V=taker_buy_base_volume, Q=taker_buy_quote_volume
        # 币安返回的是毫秒级时间戳，统一转换为纳秒级
        kline_data = {
            "exchange": processed["exchange"],
            "symbol": k.get("s", processed.get("s", "")),
            "data_type": "kline",
            "open_time": normalize_to_nanoseconds(k.get("t"), input_precision="ms") if k.get("t") else None,
            "close_time": normalize_to_nanoseconds(k.get("T"), input_precision="ms") if k.get("T") else None,
            "timestamp": normalize_to_nanoseconds(k.get("t"), input_precision="ms") if k.get("t") else None,
            "open": k.get("o"),
            "high": k.get("h"),
            "low": k.get("l"),
            "close": k.get("c"),
            "volume": k.get("v"),
            "quote_volume": k.get("q"),
            "trades": k.get("n"),
            "taker_buy_base_volume": k.get("V"),
            "taker_buy_quote_volume": k.get("Q"),
            "interval": k.get("i"),
            "is_final": k.get("x", False),
            "processed_timestamp": processed["processed_timestamp"],
            # 保留原始k数据
            "k": k,
        }

        # 验证必要字段
        if not kline_data["open_time"] or not kline_data["close_time"]:
            logger.warning(
                f"K线数据缺少时间字段: open_time={kline_data['open_time']}, close_time={kline_data['close_time']}"
            )
            return None

        logger.debug(
            f"[KlinePush] 币安K线数据处理完成: symbol={kline_data['symbol']}, interval={kline_data['interval']}, close={kline_data['close']}"
        )

        return kline_data

    def _process_binance_depth(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """
        处理币安深度数据

        兼容两种来源：
        - depth20 快照流 raw 信封：{channel, lastUpdateId, bids, asks}（无 E/s 字段，
          symbol/exchange/data_type 已由 engine 注入）
        - 已解析长键 dict：symbol/event_time/last_update_id…
        时间戳统一毫秒；快照流缺事件时间时用接受时刻兜底。
        """
        bids = message.get("bids") or []
        asks = message.get("asks") or []
        if not bids and not asks:
            return None

        symbol = str(message.get("symbol") or message.get("s") or "")
        event_time = message.get("event_time") or message.get("E")
        # 快照流缺失事件时间（E），用接受时刻兜底，毫秒与前端 kline.t 口径一致
        ts_ms = int(event_time) if event_time else int(time.time() * 1000)

        return {
            "exchange": message.get("exchange", "binance"),
            "symbol": symbol.upper(),
            "data_type": "depth",
            "timestamp": ts_ms,
            "last_update_id": message.get("last_update_id", message.get("lastUpdateId")),
            "bids": [[float(p), float(q)] for p, q in bids][:50],
            "asks": [[float(p), float(q)] for p, q in asks][:50],
            "processed_timestamp": int(time.time() * 1_000_000_000),
        }

    def _process_binance_aggtrade(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """
        处理币安聚合交易数据

        兼容 raw aggTrade 短键（{e,E,s,a,p,q,f,l,T,m}）与已解析长键；
        缺价格/数量视为不可用消息直接丢弃。
        """
        price = message.get("price", message.get("p"))
        quantity = message.get("quantity", message.get("q"))
        if price is None or quantity is None:
            logger.warning("aggTrade 缺少价格/数量字段，丢弃: %s", list(message.keys()))
            return None

        # 成交时间优先级：T（撮合时间，毫秒）> E（事件时间）> 接受时刻兜底
        trade_time = message.get("trade_time") or message.get("T") or message.get("E")
        if not trade_time:
            trade_time = int(time.time() * 1000)

        return {
            "exchange": message.get("exchange", "binance"),
            "symbol": str(message.get("symbol") or message.get("s") or "").upper(),
            "data_type": "aggTrade",
            "timestamp": int(trade_time),
            "agg_trade_id": message.get("agg_trade_id", message.get("a")),
            "price": float(price),
            "quantity": float(quantity),
            "first_trade_id": message.get("first_trade_id", message.get("f")),
            "last_trade_id": message.get("last_trade_id", message.get("l")),
            "is_buyer_maker": bool(message.get("is_buyer_maker", message.get("m", False))),
            "processed_timestamp": int(time.time() * 1_000_000_000),
        }

    def _process_binance_trade(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        处理币安交易数据

        Args:
            message: 待处理的交易消息

        Returns:
            Dict[str, Any]: 处理后的交易数据
        """
        # 调用通用处理方法
        processed = self._process_generic(message)

        # 标准化交易数据字段名
        trade_standard = {
            "exchange": processed["exchange"],
            "symbol": processed["symbol"],
            "data_type": "trade",
            "timestamp": processed["trade_time"],
            "trade_id": processed["trade_id"],
            "price": processed["price"],
            "quantity": processed["quantity"],
            "buyer_order_id": processed["buyer_order_id"],
            "seller_order_id": processed["seller_order_id"],
            "is_buyer_maker": processed["is_buyer_maker"],
            "processed_timestamp": processed["processed_timestamp"],
        }

        return trade_standard

    def _process_binance_ticker(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        处理币安完整行情数据

        Args:
            message: 待处理的完整行情消息

        Returns:
            Dict[str, Any]: 处理后的完整行情数据
        """
        # 调用通用处理方法
        processed = self._process_generic(message)

        # 标准化完整行情数据字段名
        ticker_standard = {
            "exchange": processed["exchange"],
            "symbol": processed["symbol"],
            "data_type": "ticker",
            "timestamp": processed["event_time"],
            "price_change": processed["price_change"],
            "price_change_percent": processed["price_change_percent"],
            "weighted_avg_price": processed["weighted_avg_price"],
            "prev_close_price": processed["prev_close_price"],
            "last_price": processed["last_price"],
            "last_quantity": processed["last_quantity"],
            "bid_price": processed["bid_price"],
            "bid_quantity": processed["bid_quantity"],
            "ask_price": processed["ask_price"],
            "ask_quantity": processed["ask_quantity"],
            "open_price": processed["open_price"],
            "high_price": processed["high_price"],
            "low_price": processed["low_price"],
            "volume": processed["volume"],
            "quote_volume": processed["quote_volume"],
            "trade_count": processed["trade_count"],
            "processed_timestamp": processed["processed_timestamp"],
        }

        return ticker_standard

    def _process_binance_miniTicker(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        处理币安迷你行情数据

        Args:
            message: 待处理的迷你行情消息

        Returns:
            Dict[str, Any]: 处理后的迷你行情数据
        """
        # 调用通用处理方法
        processed = self._process_generic(message)

        # 标准化迷你行情数据字段名
        mini_ticker_standard = {
            "exchange": processed["exchange"],
            "symbol": processed["symbol"],
            "data_type": "miniTicker",
            "timestamp": processed["event_time"],
            "open_price": processed["open_price"],
            "high_price": processed["high_price"],
            "low_price": processed["low_price"],
            "close_price": processed["close_price"],
            "volume": processed["volume"],
            "quote_volume": processed["quote_volume"],
            "processed_timestamp": processed["processed_timestamp"],
        }

        return mini_ticker_standard

    def _process_binance_bookTicker(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        处理币安最优买卖盘数据

        Args:
            message: 待处理的最优买卖盘消息

        Returns:
            Dict[str, Any]: 处理后的最优买卖盘数据
        """
        # 调用通用处理方法
        processed = self._process_generic(message)

        # 标准化最优买卖盘数据字段名
        book_ticker_standard = {
            "exchange": processed["exchange"],
            "symbol": processed["symbol"],
            "data_type": "bookTicker",
            "timestamp": processed["transaction_time"],
            "bid_price": processed["bid_price"],
            "bid_quantity": processed["bid_quantity"],
            "ask_price": processed["ask_price"],
            "ask_quantity": processed["ask_quantity"],
            "processed_timestamp": processed["processed_timestamp"],
        }

        return book_ticker_standard
