"""
事件驱动策略基类

基于 axon-quant 事件驱动架构的策略基类，支持高性能回测和实盘交易。
所有订单创建和事件构建都通过 axon_bridge 适配层进行。

包含:
    - EventDrivenStrategyConfig: 事件驱动策略配置基类
    - EventDrivenStrategy: 事件驱动策略基类

作者: QuantCell Team
版本: 3.0.0
日期: 2026-08-14
"""

from __future__ import annotations

import datetime as dt
import re
from abc import abstractmethod
from decimal import Decimal
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


# 引擎内部品种 key 不带分隔符（如 ETHUSDT），而策略配置/前端常传 "ETH/USDT"、"ETH-USDT"。
# 所有品种 ID 查找必须先经过这里归一化，否则查不到 instrument 导致订单全部被拒。
def normalize_instrument_id(instrument_id: Any) -> str:
    return re.sub(r"[/\-_. ]", "", str(instrument_id))


def _get_axon_bridge():
    """延迟导入 axon_bridge，避免启动时加载"""
    import axon_bridge

    return axon_bridge


class EventDrivenStrategyConfig:
    """
    事件驱动策略配置基类

    所有事件驱动策略都需要继承此配置类
    提供基础的配置参数，子类可以扩展更多特定参数

    统一使用列表形式支持单品种和多品种回测，通过列表长度自动判断模式。

    Parameters
    ----------
    instrument_ids : list[Any]
        策略交易的品种ID列表，单品种时传 [instrument_id]
    bar_types : list[Any]
        策略订阅的K线类型列表，单品种时传 [bar_type]
    trade_size : Decimal
        每笔交易的数量
    log_level : str, default "INFO"
        日志级别，可选值: DEBUG, INFO, WARNING, ERROR
    """

    def __init__(
        self,
        instrument_ids: list[Any],
        bar_types: list[Any],
        trade_size: Decimal,
        log_level: str = "INFO",
    ):
        if not instrument_ids or not bar_types:
            msg = "instrument_ids 和 bar_types 不能为空列表"
            raise ValueError(msg)
        if len(instrument_ids) != len(bar_types):
            msg = f"instrument_ids ({len(instrument_ids)}) 和 bar_types ({len(bar_types)}) 长度必须相同"
            raise ValueError(msg)

        self.instrument_ids = list(instrument_ids)
        self.bar_types = list(bar_types)
        self.instrument_id = instrument_ids[0]
        self.bar_type = bar_types[0]
        self.trade_size = trade_size
        self.log_level = log_level

    @property
    def is_multi_symbol(self) -> bool:
        return len(self.instrument_ids) > 1

    def get_instrument_index(self, instrument_id: Any) -> int:
        for i, inst_id in enumerate(self.instrument_ids):
            if inst_id == instrument_id:
                return i
        return -1

    def get_bar_type_for(self, instrument_id: Any) -> Any:
        idx = self.get_instrument_index(instrument_id)
        return self.bar_types[idx] if idx >= 0 else None


class EventDrivenStrategy:
    """
    事件驱动策略基类（基于 axon-quant）

    为 QuantCell 项目提供统一的事件驱动策略封装
    通过 engine._engine_ref 引用 axon_quant.BacktestEngine，
    使用 push_event 接口提交订单。

    子类需要实现以下方法:
    - `on_bar`: 处理K线数据的核心交易逻辑
    - `_on_bar_impl`: K线数据处理的具体实现

    Parameters
    ----------
    config : EventDrivenStrategyConfig
        策略配置对象
    """

    def __init__(self, config: EventDrivenStrategyConfig) -> None:
        self.config = config

        # 引擎引用（由 engine.add_strategy() 注入）
        self._engine_ref: Any | None = None

        # 交易品种 instrument dict 映射
        self._instruments: dict[str, dict] = {}

        # 订单状态跟踪
        self._active_orders: dict[str, dict] = {}
        self._position_qty: dict[str, float] = {}
        self._position_avg_px: dict[str, float] = {}

        # 订单 ID 计数器
        self._order_id_counter: int = 0

        # 当前 bar 的纳秒时间戳：下单/撤单事件必须使用回测的模拟时间，
        # 不能用墙上时钟，否则引擎成交记录会全部记成回测运行的当下时刻
        self._current_bar_ts_ns: int = 0

        # 统计信息
        self.bars_processed: int = 0
        self.start_time: dt.datetime | None = None
        self.end_time: dt.datetime | None = None

    def _next_order_id(self) -> str:
        """生成唯一订单 ID"""
        self._order_id_counter += 1
        return f"order_{self._order_id_counter:08d}"

    def on_start(self) -> None:
        """
        策略启动时调用

        执行以下操作:
        1. 记录策略启动时间
        2. 初始化品种信息
        3. 输出启动日志
        """
        self.start_time = dt.datetime.now()
        logger.info(f"策略启动时间: {self.start_time}")

        if self._engine_ref is None:
            logger.warning("策略未绑定引擎引用，交易功能不可用")
            return

        engine = self._engine_ref
        for raw_id in self.config.instrument_ids:
            instrument_id = normalize_instrument_id(raw_id)
            instrument = engine.get_instrument(instrument_id)
            if instrument is None:
                # 明确告警而不是静默跳过：加载失败的品种下单时必然全部被拒
                logger.warning(f"引擎中未找到交易品种: {raw_id} (归一化为 {instrument_id})")
                continue
            self._instruments[instrument_id] = instrument
            self._position_qty[instrument_id] = 0.0
            self._position_avg_px[instrument_id] = 0.0

        logger.info(f"已加载 {len(self._instruments)} 个交易品种")

    def on_bar(self, bar: dict[str, Any]) -> None:
        """
        收到K线数据时调用

        这是策略的核心方法，子类必须实现具体的交易逻辑

        Args:
            bar: K线数据字典，包含 open/high/low/close/volume/timestamp 等
        """
        self.bars_processed += 1
        # 记录当前 bar 的模拟时间，供本 bar 内下单/撤单事件使用
        self._current_bar_ts_ns = int(bar.get("timestamp") or bar.get("ts_event") or 0)
        logger.debug(f"处理K线数据: {bar.get('ts_event', 0)}, 收盘价: {bar.get('close', 0)}")
        self._on_bar_impl(bar)

    def _event_ts_ns(self) -> int:
        """订单/撤单事件使用的纳秒时间戳。

        回测中必须等于当前 bar 的历史时间（引擎据此推进模拟时钟、生成成交时间）；
        仅当策略在 on_bar 之外（异常路径）被调用时才回退到墙上时钟。
        """
        if self._current_bar_ts_ns > 0:
            return self._current_bar_ts_ns
        return _get_axon_bridge().get_current_ns_timestamp()

    @abstractmethod
    def _on_bar_impl(self, bar: dict[str, Any]) -> None:
        """
        K线数据处理的具体实现（子类必须实现）

        Args:
            bar: K线数据字典
        """
        msg = "子类必须实现 _on_bar_impl 方法"
        raise NotImplementedError(msg)

    def on_stop(self) -> None:
        """
        策略停止时调用

        执行以下操作:
        1. 记录策略停止时间
        2. 取消所有未成交订单
        3. 输出统计日志
        """
        self.end_time = dt.datetime.now()

        self._cancel_all_orders()

        duration = self.end_time - self.start_time if self.start_time else None
        logger.info("=" * 50)
        logger.info("策略运行统计:")
        logger.info(f"  启动时间: {self.start_time}")
        logger.info(f"  停止时间: {self.end_time}")
        logger.info(f"  运行时长: {duration}")
        logger.info(f"  处理K线: {self.bars_processed} 条")
        logger.info(f"  持仓品种: {list(self._position_qty.keys())}")
        logger.info("=" * 50)

    def buy(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: str = "MARKET",
        time_in_force: str = "GTC",
        instrument_id: Any | None = None,
    ) -> str | None:
        """
        买入下单

        通过 axon_bridge 适配层创建订单并提交到引擎。

        Args:
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 订单价格，市价单不需要
            order_type: 订单类型，"MARKET" 或 "LIMIT"
            time_in_force: 订单有效时间，"GTC"/"IOC"/"FOK"
            instrument_id: 品种ID，默认使用配置中的 instrument_id

        Returns:
            str: 订单 ID，下单失败返回 None
        """
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        qty = float(quantity) if quantity else float(self.config.trade_size)

        instrument = self._instruments.get(target_id)
        if instrument is None:
            logger.error(f"无法找到交易品种: {target_id}")
            return None

        order_id = self._next_order_id()

        try:
            bridge = _get_axon_bridge()
            ts_ns = self._event_ts_ns()

            order_id_int = int(self._order_id_counter)

            if order_type == "MARKET":
                order_dict = bridge.create_market_order(
                    symbol=target_id,
                    side="Buy",
                    quantity=qty,
                    order_id=order_id_int,
                    instrument=instrument,
                )
            else:
                order_dict = bridge.create_limit_order(
                    symbol=target_id,
                    side="Buy",
                    quantity=qty,
                    price=float(price) if price else 0,
                    order_id=order_id_int,
                    instrument=instrument,
                    tif=time_in_force,
                )

            # 通过引擎的 submit_order 方法提交订单
            if self._engine_ref:
                self._engine_ref.submit_order(order_dict, ts_ns)
            else:
                logger.error("引擎引用不存在，无法提交订单")
                return None

            self._active_orders[order_id] = {
                "order_id": order_id,
                "side": "Buy",
                "quantity": qty,
                "price": float(price) if price else 0,
                "instrument_id": target_id,
                "order_type": order_type,
            }

            logger.info(f"买入下单: {target_id}, 数量: {qty}, 类型: {order_type}")
            return order_id

        except Exception as e:
            logger.error(f"买入下单失败: {e}")
            return None

    def sell(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: str = "MARKET",
        time_in_force: str = "GTC",
        instrument_id: Any | None = None,
    ) -> str | None:
        """
        卖出下单

        通过 axon_bridge 适配层创建订单并提交到引擎。

        Args:
            quantity: 交易数量
            price: 订单价格
            order_type: 订单类型
            time_in_force: 订单有效时间
            instrument_id: 品种ID

        Returns:
            str: 订单 ID，下单失败返回 None
        """
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        qty = float(quantity) if quantity else float(self.config.trade_size)

        instrument = self._instruments.get(target_id)
        if instrument is None:
            logger.error(f"无法找到交易品种: {target_id}")
            return None

        order_id = self._next_order_id()

        try:
            bridge = _get_axon_bridge()
            ts_ns = self._event_ts_ns()

            order_id_int = int(self._order_id_counter)

            if order_type == "MARKET":
                order_dict = bridge.create_market_order(
                    symbol=target_id,
                    side="Sell",
                    quantity=qty,
                    order_id=order_id_int,
                    instrument=instrument,
                )
            else:
                order_dict = bridge.create_limit_order(
                    symbol=target_id,
                    side="Sell",
                    quantity=qty,
                    price=float(price) if price else 0,
                    order_id=order_id_int,
                    instrument=instrument,
                    tif=time_in_force,
                )

            # 通过引擎的 submit_order 方法提交订单
            if self._engine_ref:
                self._engine_ref.submit_order(order_dict, ts_ns)
            else:
                logger.error("引擎引用不存在，无法提交订单")
                return None

            self._active_orders[order_id] = {
                "order_id": order_id,
                "side": "Sell",
                "quantity": qty,
                "price": float(price) if price else 0,
                "instrument_id": target_id,
                "order_type": order_type,
            }

            logger.info(f"卖出下单: {target_id}, 数量: {qty}, 类型: {order_type}")
            return order_id

        except Exception as e:
            logger.error(f"卖出下单失败: {e}")
            return None

    def close_position(self, position: Any | None = None, instrument_id: Any | None = None) -> str | None:
        """
        平仓

        通过 axon_bridge 适配层创建市价订单并提交到引擎。

        Args:
            position: 未使用（兼容接口）
            instrument_id: 品种ID

        Returns:
            str: 订单 ID
        """
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        qty = abs(self._position_qty.get(target_id, 0))
        if qty <= 0:
            logger.info(f"{target_id} 无持仓可平")
            return None

        side = "Sell" if self._position_qty.get(target_id, 0) > 0 else "Buy"
        order_id = self._next_order_id()

        try:
            bridge = _get_axon_bridge()
            ts_ns = self._event_ts_ns()
            instrument = self._instruments.get(target_id)

            if instrument is None:
                logger.error(f"无法找到交易品种: {target_id}")
                return None

            order_id_int = int(self._order_id_counter)

            order_dict = bridge.create_market_order(
                symbol=target_id,
                side=side,
                quantity=qty,
                order_id=order_id_int,
                instrument=instrument,
            )

            # 通过引擎的 submit_order 方法提交订单
            if self._engine_ref:
                self._engine_ref.submit_order(order_dict, ts_ns)
            else:
                logger.error("引擎引用不存在，无法提交订单")
                return None

            logger.info(f"平仓: {target_id}, 数量: {qty}, 方向: {side}")
            return order_id

        except Exception as e:
            logger.error(f"平仓失败: {e}")
            return None

    def _cancel_all_orders(self) -> None:
        """取消所有未成交订单"""
        if self._engine_ref:
            bridge = _get_axon_bridge()
            ts_ns = self._event_ts_ns()

            for order_id, order_info in list(self._active_orders.items()):
                try:
                    cancel_event = bridge.create_cancel_order_event(
                        order_id=int(order_id.replace("order_", "")),
                        instrument=self._instruments.get(order_info["instrument_id"], {}),
                        timestamp_ns=ts_ns,
                    )
                    self._engine_ref.submit_order(cancel_event, ts_ns)
                except Exception as e:
                    logger.debug(f"取消订单 {order_id} 失败: {e}")
        self._active_orders.clear()

    def sync_positions(self) -> None:
        """
        从引擎同步净持仓到本地缓存

        事件引擎在每根 bar 撮合完成后调用。策略本身不感知成交事件，
        is_long/is_short/close_position 依赖这里的最新净持仓。
        """
        if self._engine_ref is None:
            return
        for inst_id, instrument in self._instruments.items():
            self._position_qty[inst_id] = self._engine_ref.get_engine_position(instrument)

    def get_position(self, instrument_id: Any | None = None) -> dict[str, Any]:
        """
        获取持仓信息

        Args:
            instrument_id: 品种ID

        Returns:
            Dict: 持仓信息字典
        """
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        return {
            "symbol": target_id,
            "quantity": self._position_qty.get(target_id, 0),
            "avg_price": self._position_avg_px.get(target_id, 0),
        }

    def get_position_size(self, instrument_id: Any | None = None) -> Decimal:
        """
        获取持仓数量

        Args:
            instrument_id: 品种ID

        Returns:
            Decimal: 持仓数量，正数表示多头，负数表示空头
        """
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        return Decimal(str(self._position_qty.get(target_id, 0)))

    def is_flat(self, instrument_id: Any | None = None) -> bool:
        """检查是否空仓"""
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        return self._position_qty.get(target_id, 0) == 0

    def is_long(self, instrument_id: Any | None = None) -> bool:
        """检查是否持有多头"""
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        return self._position_qty.get(target_id, 0) > 0

    def is_short(self, instrument_id: Any | None = None) -> bool:
        """检查是否持有空头"""
        target_id = normalize_instrument_id(instrument_id or self.config.instrument_id)
        return self._position_qty.get(target_id, 0) < 0

    def log_info(self, message: str) -> None:
        logger.info(message)

    def log_debug(self, message: str) -> None:
        logger.debug(message)

    def log_warning(self, message: str) -> None:
        logger.warning(message)

    def log_error(self, message: str) -> None:
        logger.error(message)

    def calculate_indicators(self, bar: dict[str, Any]) -> dict[str, Any]:
        """计算技术指标（子类可以重写）"""
        return {}

    def generate_signals(self, indicators: dict[str, Any]) -> dict[str, bool]:
        """生成交易信号（子类可以重写）"""
        return {
            "entry_long": False,
            "exit_long": False,
            "entry_short": False,
            "exit_short": False,
        }
