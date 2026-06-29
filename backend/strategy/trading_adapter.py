# -*- coding: utf-8 -*-
"""
实盘交易适配器模块

提供 QuantCell 策略与 axon_quant 交易引擎之间的适配功能。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-24
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.STRATEGY)

from strategy.core.data_types import (
    Bar as QCBar,
    InstrumentId as QCInstrumentId,
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
)
from strategy.core.strategy import StrategyConfig as QCStrategyConfig
from strategy.core.strategy import StrategyBase as QCStrategyBase


class TradingAdapterError(Exception):
    """交易适配器异常基类"""
    pass


class StrategyAdapterConfigError(TradingAdapterError):
    """配置错误"""
    pass


class StrategyLoadError(TradingAdapterError):
    """策略加载错误"""
    pass


class TradingStrategyAdapter:
    """
    实盘交易策略适配器类

    将 QuantCell 策略包装为 axon_quant 交易引擎可执行的策略。

    Attributes
    ----------
    qc_strategy : QCStrategyBase
        QuantCell 策略实例
    config : dict
        交易配置
    is_paused : bool
        策略是否暂停
    bars_processed : int
        已处理的 K 线数量
    """

    def __init__(
        self,
        qc_strategy: QCStrategyBase,
        config: Any,
    ) -> None:
        """
        初始化适配器

        Parameters
        ----------
        qc_strategy : QCStrategyBase
            QuantCell 策略实例
        config : dict
            交易配置
        """
        if not isinstance(qc_strategy, QCStrategyBase):
            raise StrategyAdapterConfigError(
                f"qc_strategy 必须是 QCStrategyBase 的子类，"
                f"实际类型: {type(qc_strategy).__name__}"
            )

        self.qc_strategy = qc_strategy
        self.config = config
        self._is_paused = False
        self._bars_processed = 0
        self._ticks_processed = 0
        self._start_time: Optional[datetime] = None

        logger.info(f"交易策略适配器已初始化: {qc_strategy.__class__.__name__}")

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def bars_processed(self) -> int:
        return self._bars_processed

    @property
    def ticks_processed(self) -> int:
        return self._ticks_processed

    def on_bar(self, bar: QCBar) -> None:
        """处理 K 线数据"""
        if self._is_paused:
            return

        self._bars_processed += 1
        self.qc_strategy.on_bar(bar)

    def on_start(self) -> None:
        """策略启动"""
        self._start_time = datetime.now()
        self.qc_strategy.on_start()
        logger.info("策略已启动")

    def on_stop(self) -> None:
        """策略停止"""
        self.qc_strategy.on_stop()
        logger.info("策略已停止")

    def pause(self) -> None:
        """暂停策略"""
        self._is_paused = True
        logger.info("策略已暂停")

    def resume(self) -> None:
        """恢复策略"""
        self._is_paused = False
        logger.info("策略已恢复")


def create_adapter(
    strategy_name: str,
    strategy_params: Dict[str, Any],
    trading_config: Dict[str, Any],
) -> TradingStrategyAdapter:
    """
    创建交易适配器实例

    Parameters
    ----------
    strategy_name : str
        策略名称
    strategy_params : dict
        策略参数
    trading_config : dict
        交易配置

    Returns
    -------
    TradingStrategyAdapter
        适配器实例
    """
    # 动态加载策略模块
    module_path = f"strategies.{strategy_name}"
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise StrategyAdapterConfigError(f"无法加载策略模块 {module_path}: {e}")

    # 查找策略类
    strategy_class = None
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, QCStrategyBase) and obj is not QCStrategyBase:
            strategy_class = obj
            break

    if strategy_class is None:
        raise StrategyAdapterConfigError(f"在 {module_path} 中未找到策略类")

    # 创建策略实例
    qc_config = QCStrategyConfig(**strategy_params)
    qc_strategy = strategy_class(qc_config)

    # 创建适配器
    adapter = TradingStrategyAdapter(qc_strategy, trading_config)

    return adapter


# =============================================================================
# 数据转换函数（兼容 axon_quant / nautilus 等多框架）
# =============================================================================

def _safe_get(obj: Any, *attrs: str, default: Any = None) -> Any:
    """链式获取属性，任意一段为 None 时返回 default。"""
    cur: Any = obj
    for a in attrs:
        if cur is None:
            return default
        cur = getattr(cur, a, None)
    return cur if cur is not None else default


def _ts_event_to_datetime(ts_event: Any) -> datetime:
    """将纳秒时间戳转换为 datetime。"""
    if ts_event is None:
        return datetime.now()
    try:
        return datetime.fromtimestamp(int(ts_event) / 1e9)
    except (TypeError, ValueError, OSError):
        return datetime.now()


def _bar_type_str(mock_bar: Any) -> str:
    """从 axon_quant Bar 派生标准化 bar_type 字符串。"""
    step = _safe_get(mock_bar, "bar_type", "spec", "step", default=1)
    agg = _safe_get(mock_bar, "bar_type", "spec", "aggregation", "name", default="MINUTE")
    try:
        step_int = int(step)
    except (TypeError, ValueError):
        step_int = 1
    return f"{step_int}-{str(agg).upper()}"


def convert_bar_to_qc(bar: Any) -> QCBar:
    """
    将 axon_quant Bar 转换为 QuantCell Bar。

    Parameters
    ----------
    bar : Any
        axon_quant Bar 实例（支持 Mock，便于测试）。

    Returns
    -------
    QCBar
        QuantCell Bar 对象
    """
    symbol = str(_safe_get(bar, "bar_type", "instrument_id", "symbol", default=""))
    venue = str(_safe_get(bar, "bar_type", "instrument_id", "venue", default=""))

    return QCBar(
        instrument_id=QCInstrumentId(symbol=symbol, venue=venue),
        bar_type=_bar_type_str(bar),
        open=float(_safe_get(bar, "open", default=0.0)),
        high=float(_safe_get(bar, "high", default=0.0)),
        low=float(_safe_get(bar, "low", default=0.0)),
        close=float(_safe_get(bar, "close", default=0.0)),
        volume=float(_safe_get(bar, "volume", default=0.0)),
        timestamp=_ts_event_to_datetime(_safe_get(bar, "ts_event")),
        ts_event=_safe_get(bar, "ts_event"),
    )


def convert_tick_to_qc(tick: Any) -> Dict[str, Any]:
    """
    将 axon_quant QuoteTick 转换为 QuantCell 行情字典。

    Parameters
    ----------
    tick : Any
        axon_quant QuoteTick 实例

    Returns
    -------
    Dict[str, Any]
        标准化的行情字典
    """
    return {
        "type": "quote",
        "symbol": str(_safe_get(tick, "instrument_id", "symbol", default="")),
        "venue": str(_safe_get(tick, "instrument_id", "venue", default="")),
        "bid_price": float(_safe_get(tick, "bid_price", default=0.0)),
        "ask_price": float(_safe_get(tick, "ask_price", default=0.0)),
        "bid_size": float(_safe_get(tick, "bid_size", default=0.0)),
        "ask_size": float(_safe_get(tick, "ask_size", default=0.0)),
        "ts_event": _safe_get(tick, "ts_event"),
        "timestamp": _ts_event_to_datetime(_safe_get(tick, "ts_event")),
    }


def convert_order_to_trading(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 QuantCell 订单字典转换为 axon_quant 交易引擎订单字典。

    Parameters
    ----------
    order : Dict[str, Any]
        QuantCell 订单字典

    Returns
    -------
    Dict[str, Any]
        axon_quant 订单字典
    """
    instrument_id = order.get("instrument_id")
    side = order.get("side")
    order_type = order.get("order_type")
    quantity = order.get("quantity")
    price = order.get("price")
    time_in_force = order.get("time_in_force")

    if instrument_id is None:
        raise StrategyAdapterConfigError("订单缺少 instrument_id")
    if not isinstance(side, OrderSide):
        raise StrategyAdapterConfigError("订单 side 必须是 OrderSide 枚举")
    if not isinstance(order_type, OrderType):
        raise StrategyAdapterConfigError("订单 order_type 必须是 OrderType 枚举")
    if not isinstance(quantity, Decimal):
        raise StrategyAdapterConfigError("订单 quantity 必须是 Decimal 类型")

    return {
        "instrument_id": str(instrument_id),
        "side": side.value,
        "order_type": order_type.value,
        "quantity": float(quantity),
        "price": float(price) if isinstance(price, Decimal) else price,
        "time_in_force": time_in_force.value if isinstance(time_in_force, TimeInForce) else time_in_force,
    }


def convert_position_to_qc(position: Any) -> Dict[str, Any]:
    """
    将 axon_quant Position 转换为 QuantCell 持仓字典。

    Parameters
    ----------
    position : Any
        axon_quant Position 实例

    Returns
    -------
    Dict[str, Any]
        QuantCell 持仓字典
    """
    qty = _safe_get(position, "quantity", default=Decimal("0"))
    if not isinstance(qty, Decimal):
        try:
            qty = Decimal(str(qty))
        except Exception:  # pragma: no cover - 健壮性兜底
            qty = Decimal("0")

    return {
        "symbol": str(_safe_get(position, "instrument_id", "symbol", default="")),
        "venue": str(_safe_get(position, "instrument_id", "venue", default="")),
        "quantity": qty,
        "side": str(_safe_get(position, "side", default="FLAT")),
        "avg_price": float(_safe_get(position, "avg_px_open", default=0.0)),
        "unrealized_pnl": float(_safe_get(position, "unrealized_pnl", default=0.0)),
        "realized_pnl": float(_safe_get(position, "realized_pnl", default=0.0)),
        "is_open": bool(_safe_get(position, "is_open", default=True)),
        "ts_opened": _safe_get(position, "ts_opened"),
    }


# =============================================================================
# 策略加载（按文件路径或模块名加载 QuantCell 策略）
# =============================================================================

def _is_strategy_subclass(obj: Any) -> bool:
    """判断 obj 是否为可实例化的 QCStrategyBase 子类。"""
    if not inspect.isclass(obj):
        return False
    if obj is QCStrategyBase:
        return False
    try:
        return issubclass(obj, QCStrategyBase)
    except TypeError:
        return False


def _is_config_subclass(obj: Any) -> bool:
    """判断 obj 是否为可实例化的 QCStrategyConfig 子类。"""
    if not inspect.isclass(obj):
        return False
    if obj is QCStrategyConfig:
        return False
    try:
        return issubclass(obj, QCStrategyConfig)
    except TypeError:
        return False


def load_quantcell_strategy(
    file_path: str,
    params: Optional[Dict[str, Any]] = None,
) -> QCStrategyBase:
    """
    从指定 Python 文件加载 QuantCell 策略并返回策略实例。

    Parameters
    ----------
    file_path : str
        策略源文件路径（.py）
    params : Dict[str, Any], optional
        策略参数

    Returns
    -------
    QCStrategyBase
        策略实例

    Raises
    ------
    StrategyLoadError
        文件不存在、未找到策略类、配置不匹配时抛出
    """
    path = Path(file_path)
    if not path.is_file():
        raise StrategyLoadError(f"策略文件不存在: {file_path}")

    params = params or {}

    module_name = f"_qc_strategy_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise StrategyLoadError(f"无法为文件创建加载规格: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise StrategyLoadError(f"执行策略文件失败: {file_path}: {e}")

    # 查找策略类与配置类
    strategy_class = None
    config_class = None
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if _is_strategy_subclass(obj):
            if strategy_class is None or obj.__name__.endswith("Strategy"):
                strategy_class = obj
        elif _is_config_subclass(obj):
            if config_class is None or obj.__name__.endswith("Config"):
                config_class = obj

    if strategy_class is None:
        raise StrategyLoadError(f"在文件 {file_path} 中未找到 QCStrategyBase 子类")

    try:
        if config_class is not None:
            config = config_class(**params)
        else:
            config = QCStrategyConfig(**params)
        return strategy_class(config)
    except Exception as e:
        raise StrategyLoadError(f"构造策略实例失败: {e}")


def create_trading_strategy_adapter(
    qc_strategy: QCStrategyBase,
    trading_config: Any,
) -> TradingStrategyAdapter:
    """
    创建交易适配器实例。

    Parameters
    ----------
    qc_strategy : QCStrategyBase
        QuantCell 策略实例
    trading_config : Any
        交易配置（dict 或 axon_quant 配置对象）

    Returns
    -------
    TradingStrategyAdapter
        适配器实例

    Raises
    ------
    StrategyAdapterConfigError
        当 qc_strategy 非法或 trading_config 缺少必要字段时
    """
    if not isinstance(qc_strategy, QCStrategyBase):
        raise StrategyAdapterConfigError(
            f"qc_strategy 必须是 QCStrategyBase 的子类，"
            f"实际类型: {type(qc_strategy).__name__}"
        )

    if not isinstance(trading_config, dict) or not trading_config:
        raise StrategyAdapterConfigError(
            "trading_config 必须是非空 dict，且至少包含 'exchange_config' 或 'config'"
        )

    return TradingStrategyAdapter(qc_strategy, trading_config)


__all__ = [
    "TradingStrategyAdapter",
    "TradingAdapterError",
    "StrategyAdapterConfigError",
    "StrategyLoadError",
    "create_adapter",
    "create_trading_strategy_adapter",
    "load_quantcell_strategy",
    "convert_bar_to_qc",
    "convert_tick_to_qc",
    "convert_order_to_trading",
    "convert_position_to_qc",
]
