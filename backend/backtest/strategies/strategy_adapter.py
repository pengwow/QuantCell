# -*- coding: utf-8 -*-
"""
回测策略适配器

将策略接口适配到 NautilusTrader 回测引擎。
策略脚本继承此适配器，可以在回测环境中运行。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-02
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Optional, List

from loguru import logger

# 导入策略接口
from strategy.core import (
    StrategyBase,
    StrategyConfig as CoreStrategyConfig,
    Bar,
    InstrumentId,
    OrderSide,
    OrderType,
    TimeInForce,
    Position,
    PositionSide,
)

# 导入 NautilusTrader
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy
from nautilus_trader.trading.config import StrategyConfig as NautilusStrategyConfig
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.identifiers import InstrumentId as NautilusInstrumentId
from nautilus_trader.model.enums import OrderSide as NautilusOrderSide, TimeInForce as NautilusTimeInForce


class StrategyConfig(CoreStrategyConfig):
    """
    回测策略配置

    继承核心策略配置，用于回测环境。
    与核心配置完全兼容。
    """
    pass


class StrategyAdapter(NautilusStrategy):
    """
    回测策略适配器

    继承 NautilusTrader 的 Strategy，将策略接口调用转换为 NautilusTrader 实现。
    这个适配器用于包装使用策略接口（StrategyBase）的策略，使其能够在回测环境中运行。

    Examples
    --------
    >>> class MyStrategy(StrategyAdapter):
    ...     def on_bar(self, bar: Bar) -> None:
    ...         if self.should_buy(bar):
    ...             self.buy(bar.instrument_id, Decimal("0.1"))
    """

    def __init__(self, config: StrategyConfig) -> None:
        """
        初始化策略适配器

        Parameters
        ----------
        config : StrategyConfig
            策略配置
        """
        # 保存统一配置
        self._unified_config = config

        # 创建 NautilusTrader 配置
        nautilus_config = NautilusStrategyConfig(
            strategy_id=config.__class__.__name__,
            order_id_tag="001",
            oms_type="NETTING",
        )

        # 初始化 NautilusTrader Strategy
        NautilusStrategy.__init__(self, nautilus_config)

        # 初始化策略状态（使用不同的属性名避免与 NautilusTrader 冲突）
        self._strategy_is_running = False
        self.bars_processed = 0
        self.start_time: Optional[dt.datetime] = None
        self.end_time: Optional[dt.datetime] = None

    @property
    def config(self) -> StrategyConfig:
        """获取策略配置"""
        return self._unified_config

    # ==================== NautilusTrader 生命周期 ====================

    def on_start(self) -> None:
        """
        策略启动（NautilusTrader 回调）

        子类可以重写此方法添加自定义启动逻辑。
        """
        self._strategy_is_running = True
        self.start_time = dt.datetime.now()
        logger.info(f"策略启动: {self.__class__.__name__}")

        # 订阅所有品种的K线数据
        for i, bar_type in enumerate(self.config.bar_types):
            instrument_id = self.config.instrument_ids[i]
            # 转换InstrumentId 到 NautilusTrader InstrumentId
            nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
            self.subscribe_bars(bar_type)
            logger.info(f"已订阅K线数据: {instrument_id} -> {bar_type}")

    def on_bar(self, bar: NautilusBar) -> None:
        """
        收到K线数据（NautilusTrader 回调）

        将 NautilusTrader Bar 转换为Bar，然后调用子类的 on_bar。
        子类应该重写此方法实现具体的交易逻辑。

        Parameters
        ----------
        bar : NautilusBar
            NautilusTrader K线数据
        """
        self.bars_processed += 1

        # 转换为Bar
        unified_bar = self._to_unified_bar(bar)

        # 子类应该重写此方法实现具体的交易逻辑
        self._on_bar_impl(unified_bar)

    def _on_bar_impl(self, bar: Bar) -> None:
        """
        K线数据处理的实现方法

        子类应该重写此方法实现具体的交易逻辑。

        Parameters
        ----------
        bar : Bar
            K线数据
        """
        pass

    def on_stop(self) -> None:
        """
        策略停止（NautilusTrader 回调）

        子类可以重写此方法添加自定义停止逻辑。
        """
        self._strategy_is_running = False
        self.end_time = dt.datetime.now()

        # 取消所有订单
        for instrument_id in self.config.instrument_ids:
            nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
            self.cancel_all_orders(nautilus_inst_id)

        logger.info(f"策略停止: {self.__class__.__name__}")

    # ==================== 交易接口实现 ====================

    def buy(
        self,
        instrument_id: InstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        买入下单

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识
        quantity : Decimal
            交易数量
        price : Optional[Decimal]
            订单价格
        order_type : OrderType
            订单类型
        time_in_force : TimeInForce
            订单有效期
        """
        # 转换统一类型到 NautilusTrader 类型
        nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)

        # 从缓存获取品种信息
        instrument = self.cache.instrument(nautilus_inst_id)
        if instrument is None:
            logger.error(f"无法找到交易品种: {instrument_id}")
            return

        # 创建数量对象
        order_qty = instrument.make_qty(quantity)

        # 创建订单
        if order_type == OrderType.MARKET:
            order = self.order_factory.market(
                instrument_id=nautilus_inst_id,
                order_side=NautilusOrderSide.BUY,
                quantity=order_qty,
            )
        else:
            order_price = instrument.make_price(price) if price else None
            order = self.order_factory.limit(
                instrument_id=nautilus_inst_id,
                order_side=NautilusOrderSide.BUY,
                quantity=order_qty,
                price=order_price,
                time_in_force=self._to_nautilus_time_in_force(time_in_force),
            )

        # 提交订单
        self.submit_order(order)
        logger.info(f"买入下单: {instrument_id}, 数量: {quantity}")

    def sell(
        self,
        instrument_id: InstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        卖出下单

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识
        quantity : Decimal
            交易数量
        price : Optional[Decimal]
            订单价格
        order_type : OrderType
            订单类型
        time_in_force : TimeInForce
            订单有效期
        """
        # 转换统一类型到 NautilusTrader 类型
        nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)

        # 从缓存获取品种信息
        instrument = self.cache.instrument(nautilus_inst_id)
        if instrument is None:
            logger.error(f"无法找到交易品种: {instrument_id}")
            return

        # 创建数量对象
        order_qty = instrument.make_qty(quantity)

        # 创建订单
        if order_type == OrderType.MARKET:
            order = self.order_factory.market(
                instrument_id=nautilus_inst_id,
                order_side=NautilusOrderSide.SELL,
                quantity=order_qty,
            )
        else:
            order_price = instrument.make_price(price) if price else None
            order = self.order_factory.limit(
                instrument_id=nautilus_inst_id,
                order_side=NautilusOrderSide.SELL,
                quantity=order_qty,
                price=order_price,
                time_in_force=self._to_nautilus_time_in_force(time_in_force),
            )

        # 提交订单
        self.submit_order(order)
        logger.info(f"卖出下单: {instrument_id}, 数量: {quantity}")

    def close_position(self, instrument_id: InstrumentId) -> None:
        """
        平仓

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识
        """
        nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
        self.close_all_positions(nautilus_inst_id)
        logger.info(f"平仓: {instrument_id}")

    def cancel_order(self, order_id: str) -> None:
        """
        取消订单

        Parameters
        ----------
        order_id : str
            订单ID
        """
        # NautilusTrader 的订单取消逻辑
        logger.info(f"取消订单: {order_id}")

    def cancel_all_orders(self, instrument_id: Optional[InstrumentId] = None) -> None:
        """
        取消所有订单

        Parameters
        ----------
        instrument_id : Optional[InstrumentId]
            品种标识，None 表示取消所有品种的订单
        """
        if instrument_id:
            nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
            NautilusStrategy.cancel_all_orders(self, nautilus_inst_id)
        else:
            for inst_id in self.config.instrument_ids:
                nautilus_inst_id = self._to_nautilus_instrument_id(inst_id)
                NautilusStrategy.cancel_all_orders(self, nautilus_inst_id)

    # ==================== 持仓查询接口实现 ====================

    def get_position(self, instrument_id: InstrumentId) -> Optional[Position]:
        """
        获取持仓信息

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        Optional[Position]
            持仓对象
        """
        nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
        positions = self.cache.positions_for_instrument(nautilus_inst_id)

        if positions:
            position = positions[0]
            # 转换为Position
            side = PositionSide.LONG if position.side.is_buy() else PositionSide.SHORT
            return Position(
                instrument_id=instrument_id,
                side=side,
                quantity=position.quantity.as_decimal(),
                avg_price=float(position.avg_px_open),
                unrealized_pnl=float(position.unrealized_pnl),
                realized_pnl=float(position.realized_pnl),
            )

        return None

    def get_position_size(self, instrument_id: InstrumentId) -> Decimal:
        """
        获取持仓数量

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        Decimal
            持仓数量
        """
        position = self.get_position(instrument_id)
        if position is None:
            return Decimal("0")

        if position.side == PositionSide.SHORT:
            return -position.quantity
        return position.quantity

    def is_flat(self, instrument_id: InstrumentId) -> bool:
        """
        检查是否空仓

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        bool
            如果没有持仓返回 True
        """
        nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
        return self.portfolio.is_flat(nautilus_inst_id)

    def is_long(self, instrument_id: InstrumentId) -> bool:
        """
        检查是否持有多头

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        bool
            如果持有多头返回 True
        """
        nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
        return self.portfolio.is_net_long(nautilus_inst_id)

    def is_short(self, instrument_id: InstrumentId) -> bool:
        """
        检查是否持有空头

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        bool
            如果持有空头返回 True
        """
        nautilus_inst_id = self._to_nautilus_instrument_id(instrument_id)
        return self.portfolio.is_net_short(nautilus_inst_id)

    # ==================== 类型转换方法 ====================

    def _to_unified_bar(self, bar: NautilusBar) -> Bar:
        """
        将 NautilusTrader Bar 转换为Bar

        Parameters
        ----------
        bar : NautilusBar
            NautilusTrader K线数据

        Returns
        -------
        Bar
            K线数据
        """
        # 转换 InstrumentId
        unified_inst_id = InstrumentId(
            symbol=bar.bar_type.instrument_id.symbol.value,
            venue=bar.bar_type.instrument_id.venue.value,
        )

        # 获取时间戳（ts_event 是纳秒时间戳）
        ts_event_ns = bar.ts_event
        from datetime import datetime
        timestamp = datetime.fromtimestamp(ts_event_ns / 1e9)

        return Bar(
            instrument_id=unified_inst_id,
            bar_type=str(bar.bar_type),
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
            timestamp=timestamp,
            ts_event=ts_event_ns,
        )

    def _to_nautilus_instrument_id(self, instrument_id: InstrumentId) -> NautilusInstrumentId:
        """
        将InstrumentId 转换为 NautilusTrader InstrumentId

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        NautilusInstrumentId
            NautilusTrader 品种标识
        """
        return NautilusInstrumentId.from_str(f"{instrument_id.symbol}.{instrument_id.venue}")

    def _to_nautilus_time_in_force(self, tif: TimeInForce) -> NautilusTimeInForce:
        """
        将统一 TimeInForce 转换为 NautilusTrader TimeInForce

        Parameters
        ----------
        tif : TimeInForce
            订单有效期

        Returns
        -------
        NautilusTimeInForce
            NautilusTrader 订单有效期
        """
        mapping = {
            TimeInForce.GTC: NautilusTimeInForce.GTC,
            TimeInForce.IOC: NautilusTimeInForce.IOC,
            TimeInForce.FOK: NautilusTimeInForce.FOK,
            TimeInForce.DAY: NautilusTimeInForce.DAY,
        }
        return mapping.get(tif, NautilusTimeInForce.GTC)


# 向后兼容：Strategy 作为 StrategyAdapter 的别名
Strategy = StrategyAdapter
