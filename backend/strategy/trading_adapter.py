# -*- coding: utf-8 -*-
"""
实盘交易适配器模块

提供 QuantCell 策略与实盘交易框架之间的适配功能，包括：
- TradingStrategyAdapter 类：将 QuantCell 策略包装为实盘交易框架策略
- 数据转换函数：在 QuantCell 和实盘交易框架数据格式之间转换
- 策略加载器函数：动态加载 QuantCell 策略并创建适配器实例

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-27
"""

from __future__ import annotations

import importlib
import inspect
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

# 使用项目日志系统
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.STRATEGY)

# 尝试导入 NautilusTrader
try:
    from nautilus_trader.trading.strategy import Strategy
    from nautilus_trader.config import StrategyConfig
    from nautilus_trader.model.data import Bar as NautilusBar
    from nautilus_trader.model.data import QuoteTick as NautilusQuoteTick
    from nautilus_trader.model.data import TradeTick as NautilusTradeTick
    from nautilus_trader.model.position import Position as NautilusPosition
    from nautilus_trader.model.enums import OrderSide as NautilusOrderSide
    from nautilus_trader.model.enums import OrderType as NautilusOrderType
    from nautilus_trader.model.enums import TimeInForce as NautilusTimeInForce
    from nautilus_trader.model.enums import PositionSide as NautilusPositionSide
    from nautilus_trader.model.identifiers import InstrumentId as NautilusInstrumentId
    from nautilus_trader.model.objects import Price, Quantity
    from nautilus_trader.model.orders.base import Order as NautilusOrder
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    Strategy = object
    StrategyConfig = None
    NautilusBar = None
    NautilusQuoteTick = None
    NautilusTradeTick = None
    NautilusPosition = None
    NautilusOrderSide = None
    NautilusOrderType = None
    NautilusTimeInForce = None
    NautilusPositionSide = None
    NautilusInstrumentId = None
    Price = None
    Quantity = None
    NautilusOrder = None
    logger.warning("NautilusTrader 未安装，实盘交易功能将不可用")

# QuantCell 内部导入
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


# =============================================================================
# 异常定义
# =============================================================================

class TradingAdapterError(Exception):
    """交易适配器异常基类"""


class StrategyLoadError(TradingAdapterError):
    """策略加载异常"""


class DataConversionError(TradingAdapterError):
    """数据转换异常"""


class StrategyAdapterConfigError(TradingAdapterError):
    """适配器配置异常"""


# =============================================================================
# TradingStrategyAdapter 类
# =============================================================================

class TradingStrategyAdapter(Strategy if NAUTILUS_AVAILABLE else object):
    """
    实盘交易策略适配器类

    将 QuantCell 策略包装为实盘交易框架策略，实现两个框架之间的桥接。
    支持生命周期管理、数据转换、订单转换等功能。

    Attributes
    ----------
    qc_strategy : QCStrategyBase
        QuantCell 策略实例
    config : StrategyConfig
        实盘交易框架策略配置
    is_paused : bool
        策略是否暂停
    bars_processed : int
        已处理的 K 线数量
    ticks_processed : int
        已处理的 Tick 数量

    Examples
    --------
    >>> from strategy.core.strategy import StrategyConfig
    >>> qc_config = QCStrategyConfig(
    ...     instrument_ids=[QCInstrumentId("BTCUSDT", "BINANCE")],
    ...     bar_types=["1-HOUR"],
    ... )
    >>> qc_strategy = MyQuantCellStrategy(qc_config)
    >>> adapter = TradingStrategyAdapter(qc_strategy, trading_config)
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
        config : StrategyConfig
            实盘交易框架策略配置

        Raises
        ------
        StrategyAdapterConfigError
            如果配置无效
        """
        # 首先验证 QuantCell 策略类型
        # 注意：这个检查必须在调用父类 __init__ 之前进行
        # 因为 Nautilus Strategy 对 config 参数有严格的类型检查
        if not isinstance(qc_strategy, QCStrategyBase):
            raise StrategyAdapterConfigError(
                f"qc_strategy 必须是 QCStrategyBase 的子类，"
                f"实际类型: {type(qc_strategy).__name__}"
            )

        # 然后调用父类初始化
        if NAUTILUS_AVAILABLE:
            super().__init__(config)
        else:
            self.config = config

        self.qc_strategy = qc_strategy
        self._is_paused = False
        self._bars_processed = 0
        self._ticks_processed = 0
        self._start_time: Optional[datetime] = None

        logger.info(
            f"实盘交易策略适配器已初始化: "
            f"策略类={type(qc_strategy).__name__}"
        )

    @property
    def is_paused(self) -> bool:
        """获取策略暂停状态"""
        return self._is_paused

    @property
    def bars_processed(self) -> int:
        """获取已处理的 K 线数量"""
        return self._bars_processed

    @property
    def ticks_processed(self) -> int:
        """获取已处理的 Tick 数量"""
        return self._ticks_processed

    def on_start(self) -> None:
        """
        策略启动时调用

        执行以下操作：
        1. 记录启动时间
        2. 调用 QuantCell 策略的 on_start 方法
        3. 输出启动日志
        """
        self._start_time = datetime.utcnow()
        logger.info(
            f"策略启动: {type(self.qc_strategy).__name__}, "
            f"时间={self._start_time.isoformat()}"
        )

        try:
            # 调用 QuantCell 策略的 on_start
            self.qc_strategy.on_start()
            logger.debug("QuantCell 策略 on_start 执行完成")
        except Exception as e:
            logger.error(f"QuantCell 策略 on_start 执行失败: {e}")
            raise

    def on_stop(self) -> None:
        """
        策略停止时调用

        执行以下操作：
        1. 调用 QuantCell 策略的 on_stop 方法
        2. 输出统计日志
        3. 清理资源
        """
        end_time = datetime.utcnow()
        duration = None
        if self._start_time:
            duration = end_time - self._start_time

        logger.info(
            f"策略停止: {type(self.qc_strategy).__name__}, "
            f"时间={end_time.isoformat()}, "
            f"运行时长={duration}, "
            f"处理 K 线={self._bars_processed}, "
            f"处理 Tick={self._ticks_processed}"
        )

        try:
            # 调用 QuantCell 策略的 on_stop
            self.qc_strategy.on_stop()
            logger.debug("QuantCell 策略 on_stop 执行完成")
        except Exception as e:
            logger.error(f"QuantCell 策略 on_stop 执行失败: {e}")
            raise

    def on_bar(self, bar: Any) -> None:
        """
        收到 K 线数据时调用

        将实盘交易框架 Bar 转换为 QuantCell 格式后传递给 QuantCell 策略处理。

        Parameters
        ----------
        bar : Bar
            实盘交易框架 K线数据对象

        Raises
        ------
        DataConversionError
            如果数据转换失败
        """
        # 检查策略是否暂停
        if self._is_paused:
            return

        try:
            # 转换数据格式
            qc_bar = convert_bar_to_qc(bar)

            # 更新统计
            self._bars_processed += 1

            # 调用 QuantCell 策略的 on_bar
            self.qc_strategy.on_bar(qc_bar)

            logger.debug(
                f"处理 K 线: {qc_bar.instrument_id}, "
                f"时间={qc_bar.timestamp.isoformat()}, "
                f"收盘价={qc_bar.close}"
            )

        except Exception as e:
            logger.error(f"处理 K 线数据失败: {e}")
            raise DataConversionError(f"K 线数据处理失败: {e}") from e

    def on_tick(self, tick: Any) -> None:
        """
        收到 Tick 数据时调用

        将实盘交易框架 Tick 转换为 QuantCell 格式后传递给 QuantCell 策略处理。

        Parameters
        ----------
        tick : Tick
            实盘交易框架 Tick 数据对象

        Raises
        ------
        DataConversionError
            如果数据转换失败
        """
        # 检查策略是否暂停
        if self._is_paused:
            return

        try:
            # 转换数据格式
            qc_tick = convert_tick_to_qc(tick)

            # 更新统计
            self._ticks_processed += 1

            # 调用 QuantCell 策略的 on_tick（如果存在）
            if hasattr(self.qc_strategy, 'on_tick'):
                self.qc_strategy.on_tick(qc_tick)

            logger.debug(
                f"处理 Tick: {qc_tick['instrument_id']}, "
                f"时间={qc_tick['timestamp']}"
            )

        except Exception as e:
            logger.error(f"处理 Tick 数据失败: {e}")
            raise DataConversionError(f"Tick 数据处理失败: {e}") from e

    def pause(self) -> None:
        """
        暂停策略执行

        暂停后，on_bar 和 on_tick 方法将不会处理新数据，
        但策略实例仍然保持运行状态。
        """
        if not self._is_paused:
            self._is_paused = True
            logger.info(f"策略已暂停: {type(self.qc_strategy).__name__}")

    def resume(self) -> None:
        """
        恢复策略执行

        恢复后，on_bar 和 on_tick 方法将继续处理新数据。
        """
        if self._is_paused:
            self._is_paused = False
            logger.info(f"策略已恢复: {type(self.qc_strategy).__name__}")

    def buy(
        self,
        instrument_id: QCInstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        买入下单（代理到 QuantCell 策略）

        Parameters
        ----------
        instrument_id : QCInstrumentId
            品种标识
        quantity : Decimal
            交易数量
        price : Optional[Decimal]
            订单价格，市价单为 None
        order_type : OrderType
            订单类型
        time_in_force : TimeInForce
            订单有效期
        """
        try:
            self.qc_strategy.buy(instrument_id, quantity, price, order_type, time_in_force)
            logger.info(f"买入下单: {instrument_id}, 数量={quantity}")
        except Exception as e:
            logger.error(f"买入下单失败: {e}")
            raise

    def sell(
        self,
        instrument_id: QCInstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        卖出下单（代理到 QuantCell 策略）

        Parameters
        ----------
        instrument_id : QCInstrumentId
            品种标识
        quantity : Decimal
            交易数量
        price : Optional[Decimal]
            订单价格，市价单为 None
        order_type : OrderType
            订单类型
        time_in_force : TimeInForce
            订单有效期
        """
        try:
            self.qc_strategy.sell(instrument_id, quantity, price, order_type, time_in_force)
            logger.info(f"卖出下单: {instrument_id}, 数量={quantity}")
        except Exception as e:
            logger.error(f"卖出下单失败: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        获取适配器统计信息

        Returns
        -------
        Dict[str, Any]
            统计信息字典
        """
        return {
            "strategy_name": type(self.qc_strategy).__name__,
            "is_paused": self._is_paused,
            "bars_processed": self._bars_processed,
            "ticks_processed": self._ticks_processed,
            "start_time": self._start_time.isoformat() if self._start_time else None,
        }


# =============================================================================
# 数据转换函数
# =============================================================================

def convert_bar_to_qc(bar: Any) -> QCBar:
    """
    将实盘交易框架 Bar 转换为 QuantCell K线格式

    Parameters
    ----------
    bar : Bar
        实盘交易框架 K线数据对象

    Returns
    -------
    QCBar
        QuantCell K线数据对象

    Raises
    ------
    DataConversionError
        如果转换失败

    Examples
    --------
    >>> trading_bar = Bar(...)
    >>> qc_bar = convert_bar_to_qc(trading_bar)
    >>> print(qc_bar.close)
    50000.0
    """
    try:
        # 提取品种信息
        if NAUTILUS_AVAILABLE and hasattr(bar, 'bar_type'):
            # Nautilus Bar 格式
            nautilus_instrument_id = bar.bar_type.instrument_id
            qc_instrument_id = QCInstrumentId(
                symbol=str(nautilus_instrument_id.symbol),
                venue=str(nautilus_instrument_id.venue),
            )

            # 提取 K 线类型
            bar_spec = bar.bar_type.spec
            bar_type_str = f"{bar_spec.step}-{bar_spec.aggregation.name}"

            # 转换时间戳
            timestamp = datetime.fromtimestamp(bar.ts_event / 1e9)

            # 创建 QuantCell Bar
            qc_bar = QCBar(
                instrument_id=qc_instrument_id,
                bar_type=bar_type_str,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume) if hasattr(bar, 'volume') else 0.0,
                timestamp=timestamp,
                ts_event=bar.ts_event,
            )
        else:
            # 通用格式
            qc_bar = QCBar(
                instrument_id=QCInstrumentId(
                    symbol=str(getattr(bar, 'symbol', 'UNKNOWN')),
                    venue=str(getattr(bar, 'venue', 'BINANCE')),
                ),
                bar_type=getattr(bar, 'bar_type', '1-HOUR'),
                open=float(getattr(bar, 'open', 0)),
                high=float(getattr(bar, 'high', 0)),
                low=float(getattr(bar, 'low', 0)),
                close=float(getattr(bar, 'close', 0)),
                volume=float(getattr(bar, 'volume', 0)),
                timestamp=datetime.utcnow(),
                ts_event=0,
            )

        return qc_bar

    except Exception as e:
        logger.error(f"Bar 转换失败: {e}")
        raise DataConversionError(f"无法将 Bar 转换为 QCBar: {e}") from e


def convert_tick_to_qc(tick: Any) -> Dict[str, Any]:
    """
    将实盘交易框架 Tick 转换为 QuantCell Tick 格式

    Parameters
    ----------
    tick : Tick
        实盘交易框架 Tick 数据对象

    Returns
    -------
    Dict[str, Any]
        QuantCell Tick 数据字典

    Raises
    ------
    DataConversionError
        如果转换失败

    Examples
    --------
    >>> trading_tick = QuoteTick(...)
    >>> qc_tick = convert_tick_to_qc(trading_tick)
    >>> print(qc_tick['bid_price'])
    50000.0
    """
    try:
        # 转换时间戳
        if hasattr(tick, 'ts_event'):
            timestamp = datetime.fromtimestamp(tick.ts_event / 1e9)
            ts_event = tick.ts_event
        else:
            timestamp = datetime.utcnow()
            ts_event = 0

        # 提取品种信息
        if hasattr(tick, 'instrument_id'):
            nautilus_instrument_id = tick.instrument_id
            qc_instrument_id = QCInstrumentId(
                symbol=str(nautilus_instrument_id.symbol),
                venue=str(nautilus_instrument_id.venue),
            )
        else:
            qc_instrument_id = QCInstrumentId(
                symbol=str(getattr(tick, 'symbol', 'UNKNOWN')),
                venue=str(getattr(tick, 'venue', 'BINANCE')),
            )

        # 根据 Tick 类型转换
        if NAUTILUS_AVAILABLE and hasattr(tick, 'bid_price'):
            # QuoteTick 转换
            return {
                "type": "quote",
                "instrument_id": qc_instrument_id,
                "symbol": str(qc_instrument_id.symbol),
                "venue": str(qc_instrument_id.venue),
                "bid_price": float(tick.bid_price),
                "bid_size": float(tick.bid_size),
                "ask_price": float(tick.ask_price),
                "ask_size": float(tick.ask_size),
                "timestamp": timestamp.isoformat(),
                "ts_event": ts_event,
            }
        elif NAUTILUS_AVAILABLE and hasattr(tick, 'price'):
            # TradeTick 转换
            aggressor_side = OrderSide.BUY if tick.aggressor_side == NautilusOrderSide.BUY else OrderSide.SELL

            return {
                "type": "trade",
                "instrument_id": qc_instrument_id,
                "symbol": str(qc_instrument_id.symbol),
                "venue": str(qc_instrument_id.venue),
                "price": float(tick.price),
                "size": float(tick.size),
                "aggressor_side": aggressor_side.value,
                "timestamp": timestamp.isoformat(),
                "ts_event": ts_event,
            }
        else:
            # 通用格式
            return {
                "type": "tick",
                "instrument_id": qc_instrument_id,
                "symbol": str(qc_instrument_id.symbol),
                "venue": str(qc_instrument_id.venue),
                "price": float(getattr(tick, 'price', 0)),
                "size": float(getattr(tick, 'size', 0)),
                "timestamp": timestamp.isoformat(),
                "ts_event": ts_event,
            }

    except Exception as e:
        logger.error(f"Tick 转换失败: {e}")
        raise DataConversionError(f"无法将 Tick 转换为 QC 格式: {e}") from e


def convert_order_to_trading(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 QuantCell 订单转换为实盘交易框架 Order 格式

    Parameters
    ----------
    order : Dict[str, Any]
        QuantCell 订单字典，包含以下字段：
        - instrument_id: 品种标识
        - side: 订单方向 ("BUY" 或 "SELL")
        - order_type: 订单类型 ("MARKET", "LIMIT", "STOP", "STOP_LIMIT")
        - quantity: 订单数量
        - price: 订单价格（可选）
        - time_in_force: 订单有效期（可选）

    Returns
    -------
    Dict[str, Any]
        实盘交易框架订单参数字典

    Raises
    ------
    DataConversionError
        如果转换失败

    Examples
    --------
    >>> qc_order = {
    ...     "instrument_id": QCInstrumentId("BTCUSDT", "BINANCE"),
    ...     "side": "BUY",
    ...     "order_type": "LIMIT",
    ...     "quantity": Decimal("0.1"),
    ...     "price": Decimal("50000"),
    ... }
    >>> trading_order = convert_order_to_trading(qc_order)
    """
    try:
        # 验证必要字段
        required_fields = ["instrument_id", "side", "order_type", "quantity"]
        for field in required_fields:
            if field not in order:
                raise ValueError(f"缺少必要字段: {field}")

        # 转换品种标识
        instrument_id = order["instrument_id"]
        if isinstance(instrument_id, QCInstrumentId):
            instrument_id_str = str(instrument_id)
        else:
            instrument_id_str = str(instrument_id)

        # 转换订单方向
        side_str = order["side"].upper() if isinstance(order["side"], str) else order["side"].value

        # 转换订单类型
        order_type_str = order["order_type"].upper() if isinstance(order["order_type"], str) else order["order_type"].value

        # 转换有效期
        tif_str = order.get("time_in_force", "GTC")
        if isinstance(tif_str, str):
            tif_str = tif_str.upper()
        else:
            tif_str = tif_str.value

        # 构建实盘交易框架订单参数
        trading_order = {
            "instrument_id": instrument_id_str,
            "side": side_str,
            "order_type": order_type_str,
            "quantity": str(order["quantity"]),
            "time_in_force": tif_str,
        }

        # 添加价格（限价单和止损单需要）
        if "price" in order and order["price"] is not None:
            trading_order["price"] = str(order["price"])

        # 添加止损价格
        if "stop_price" in order and order["stop_price"] is not None:
            trading_order["stop_price"] = str(order["stop_price"])

        return trading_order

    except Exception as e:
        logger.error(f"订单转换失败: {e}")
        raise DataConversionError(f"无法将 QC 订单转换为实盘交易格式: {e}") from e


def convert_position_to_qc(position: Any) -> Dict[str, Any]:
    """
    将实盘交易框架 Position 转换为 QuantCell 持仓格式

    Parameters
    ----------
    position : Position
        实盘交易框架持仓对象

    Returns
    -------
    Dict[str, Any]
        QuantCell 持仓格式字典

    Raises
    ------
    DataConversionError
        如果转换失败

    Examples
    --------
    >>> trading_position = Position(...)
    >>> qc_position = convert_position_to_qc(trading_position)
    >>> print(qc_position['quantity'])
    0.1
    """
    try:
        # 转换品种标识
        if hasattr(position, 'instrument_id'):
            nautilus_instrument_id = position.instrument_id
            qc_instrument_id = QCInstrumentId(
                symbol=str(nautilus_instrument_id.symbol),
                venue=str(nautilus_instrument_id.venue),
            )
        else:
            qc_instrument_id = QCInstrumentId(
                symbol=str(getattr(position, 'symbol', 'UNKNOWN')),
                venue=str(getattr(position, 'venue', 'BINANCE')),
            )

        # 转换持仓方向
        if NAUTILUS_AVAILABLE and hasattr(position, 'side'):
            if position.side == NautilusPositionSide.LONG:
                side = PositionSide.LONG
            elif position.side == NautilusPositionSide.SHORT:
                side = PositionSide.SHORT
            else:
                side = PositionSide.FLAT
        else:
            side = PositionSide.LONG if getattr(position, 'quantity', 0) > 0 else PositionSide.FLAT

        # 转换时间戳
        if hasattr(position, 'ts_opened') and position.ts_opened:
            timestamp = datetime.fromtimestamp(position.ts_opened / 1e9)
            ts_opened = position.ts_opened
        else:
            timestamp = datetime.utcnow()
            ts_opened = 0

        # 构建 QuantCell 持仓字典
        qc_position = {
            "instrument_id": qc_instrument_id,
            "symbol": str(qc_instrument_id.symbol),
            "venue": str(qc_instrument_id.venue),
            "side": side.value,
            "quantity": getattr(position, 'quantity', Decimal('0')),
            "avg_price": float(getattr(position, 'avg_px_open', 0)),
            "unrealized_pnl": float(getattr(position, 'unrealized_pnl', 0)),
            "realized_pnl": float(getattr(position, 'realized_pnl', 0)),
            "timestamp": timestamp.isoformat(),
            "ts_opened": ts_opened,
            "ts_closed": getattr(position, 'ts_closed', None),
            "is_open": getattr(position, 'is_open', False),
        }

        return qc_position

    except Exception as e:
        logger.error(f"持仓转换失败: {e}")
        raise DataConversionError(f"无法将 Position 转换为 QC 格式: {e}") from e


# =============================================================================
# 策略加载器函数
# =============================================================================

def load_quantcell_strategy(
    strategy_path: str,
    config: Dict[str, Any],
) -> QCStrategyBase:
    """
    动态加载 QuantCell 策略

    从指定路径加载策略模块，实例化策略类。

    Parameters
    ----------
    strategy_path : str
        策略文件路径或模块路径
        例如: "backend/strategies/my_strategy.py" 或 "strategies.my_strategy"
    config : Dict[str, Any]
        策略配置字典

    Returns
    -------
    QCStrategyBase
        QuantCell 策略实例

    Raises
    ------
    StrategyLoadError
        如果加载失败

    Examples
    --------
    >>> config = {
    ...     "instrument_ids": [QCInstrumentId("BTCUSDT", "BINANCE")],
    ...     "bar_types": ["1-HOUR"],
    ... }
    >>> strategy = load_quantcell_strategy("backend/strategies/sma_cross.py", config)
    """
    try:
        # 解析路径
        path = Path(strategy_path)

        if path.exists():
            # 文件路径方式加载
            module_name = path.stem
            module_dir = path.parent

            # 添加目录到 Python 路径
            if str(module_dir) not in sys.path:
                sys.path.insert(0, str(module_dir))

            # 清除模块缓存
            if module_name in sys.modules:
                del sys.modules[module_name]

            # 导入模块
            module = importlib.import_module(module_name)
        else:
            # 模块路径方式加载
            module_name = strategy_path.replace("/", ".").replace("\\", ".").rstrip(".py")

            # 清除模块缓存
            if module_name in sys.modules:
                del sys.modules[module_name]

            # 导入模块
            module = importlib.import_module(module_name)

        # 查找策略类
        strategy_class = None
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, QCStrategyBase)
                and obj is not QCStrategyBase
                and not name.endswith("Base")  # 排除基类
            ):
                strategy_class = obj
                logger.info(f"找到 QuantCell 策略类: {name}")
                break

        if strategy_class is None:
            raise StrategyLoadError(
                f"在模块 {module_name} 中找不到 QuantCell 策略类"
            )

        # 创建策略配置
        if "instrument_ids" in config:
            qc_config = QCStrategyConfig(**config)
        else:
            qc_config = QCStrategyConfig(
                instrument_ids=[QCInstrumentId("BTCUSDT", "BINANCE")],
                bar_types=["1-HOUR"],
            )

        # 实例化策略
        strategy = strategy_class(qc_config)

        # 设置额外参数
        for key, value in config.items():
            if not hasattr(qc_config, key) and not key.startswith("_"):
                setattr(strategy, key, value)

        logger.info(f"成功加载 QuantCell 策略: {strategy_class.__name__}")

        return strategy

    except Exception as e:
        logger.error(f"加载 QuantCell 策略失败: {e}")
        raise StrategyLoadError(f"无法加载策略 {strategy_path}: {e}") from e


def create_trading_strategy_adapter(
    qc_strategy: QCStrategyBase,
    config: Dict[str, Any],
) -> TradingStrategyAdapter:
    """
    创建实盘交易适配器实例

    将 QuantCell 策略包装为实盘交易框架策略适配器。

    Parameters
    ----------
    qc_strategy : QCStrategyBase
        QuantCell 策略实例
    config : Dict[str, Any]
        实盘交易框架策略配置字典，包含以下字段：
        - instrument_id: 品种标识
        - bar_type: K线类型
        - trade_size: 交易数量（可选）
        - log_level: 日志级别（可选）

    Returns
    -------
    TradingStrategyAdapter
        实盘交易框架策略适配器实例

    Raises
    ------
    StrategyAdapterConfigError
        如果配置无效

    Examples
    --------
    >>> qc_strategy = MyQuantCellStrategy(qc_config)
    >>> config = {
    ...     "instrument_id": "BTCUSDT.BINANCE",
    ...     "bar_type": "1-HOUR",
    ...     "trade_size": Decimal("0.1"),
    ... }
    >>> adapter = create_trading_strategy_adapter(qc_strategy, config)
    """
    try:
        # 验证必要配置
        if not NAUTILUS_AVAILABLE:
            logger.warning("NautilusTrader 未安装，创建基础适配器")

        # 创建适配器
        adapter = TradingStrategyAdapter(
            qc_strategy=qc_strategy,
            config=config,
        )

        logger.info(
            f"成功创建实盘交易策略适配器: "
            f"策略={type(qc_strategy).__name__}"
        )

        return adapter

    except Exception as e:
        logger.error(f"创建实盘交易策略适配器失败: {e}")
        raise StrategyAdapterConfigError(f"无法创建适配器: {e}") from e


# =============================================================================
# 便捷函数
# =============================================================================

def adapt_strategy(
    strategy_path: str,
    qc_config: Dict[str, Any],
    trading_config: Dict[str, Any],
) -> TradingStrategyAdapter:
    """
    一站式策略适配函数

    加载 QuantCell 策略并创建实盘交易框架适配器。

    Parameters
    ----------
    strategy_path : str
        策略文件路径
    qc_config : Dict[str, Any]
        QuantCell 策略配置
    trading_config : Dict[str, Any]
        实盘交易框架策略配置

    Returns
    -------
    TradingStrategyAdapter
        实盘交易框架策略适配器实例

    Examples
    --------
    >>> adapter = adapt_strategy(
    ...     strategy_path="backend/strategies/sma_cross.py",
    ...     qc_config={"instrument_ids": [...], "bar_types": [...]},
    ...     trading_config={"instrument_id": ..., "bar_type": ...},
    ... )
    """
    # 加载 QuantCell 策略
    qc_strategy = load_quantcell_strategy(strategy_path, qc_config)

    # 创建适配器
    adapter = create_trading_strategy_adapter(qc_strategy, trading_config)

    return adapter


# 模块导出
__all__ = [
    # 适配器类
    "TradingStrategyAdapter",
    # 异常类
    "TradingAdapterError",
    "StrategyLoadError",
    "DataConversionError",
    "StrategyAdapterConfigError",
    # 数据转换函数
    "convert_bar_to_qc",
    "convert_tick_to_qc",
    "convert_order_to_trading",
    "convert_position_to_qc",
    # 策略加载器函数
    "load_quantcell_strategy",
    "create_trading_strategy_adapter",
    # 便捷函数
    "adapt_strategy",
]
