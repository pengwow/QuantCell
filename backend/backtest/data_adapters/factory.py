"""DataAdapterFactory — 根据数据类型创建对应的适配器实例。"""

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class DataAdapterFactory:
    """数据适配器工厂。

    根据 data_type 创建对应的适配器实例。
    """

    _KLINE_TYPES = {
        "kline",
        "markPriceKlines",
        "indexPriceKlines",
        "premiumIndexKlines",
    }
    _TICK_TYPES = {"aggTrades", "trades"}
    _ORDERBOOK_TYPES = {"bookDepth", "bookTicker"}
    _DERIV_TYPES = {"fundingRate", "openInterest"}

    @classmethod
    def create(cls, data_type: str):
        """根据 data_type 创建对应的适配器。"""
        if data_type in cls._KLINE_TYPES:
            from .kline_adapter import KlineAdapter

            return KlineAdapter()
        elif data_type in cls._TICK_TYPES:
            from .tick_adapter import TickAdapter

            return TickAdapter()
        elif data_type in cls._ORDERBOOK_TYPES:
            from .orderbook_adapter import OrderBookAdapter

            return OrderBookAdapter()
        elif data_type in cls._DERIV_TYPES:
            from .deriv_adapter import DerivAdapter

            return DerivAdapter()
        else:
            msg = f"不支持的数据类型: {data_type}\n支持的类型: {cls.list_supported_types()}"
            raise ValueError(msg)

    @classmethod
    def list_supported_types(cls) -> list[str]:
        """列出所有支持的数据类型。"""
        return sorted(cls._KLINE_TYPES | cls._TICK_TYPES | cls._ORDERBOOK_TYPES | cls._DERIV_TYPES)

    @classmethod
    def get_adapter_class(cls, data_type: str):
        """获取适配器类（用于检查）。"""
        from .deriv_adapter import DerivAdapter
        from .kline_adapter import KlineAdapter
        from .orderbook_adapter import OrderBookAdapter
        from .tick_adapter import TickAdapter

        mapping = {}
        mapping.update({t: KlineAdapter for t in cls._KLINE_TYPES})
        mapping.update({t: TickAdapter for t in cls._TICK_TYPES})
        mapping.update({t: OrderBookAdapter for t in cls._ORDERBOOK_TYPES})
        mapping.update({t: DerivAdapter for t in cls._DERIV_TYPES})

        return mapping.get(data_type)
