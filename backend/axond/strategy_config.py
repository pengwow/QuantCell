# -*- coding: utf-8 -*-
"""策略配置基类"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

from .types import InstrumentId


@dataclass
class StrategyConfig:
    """策略配置基类。

    支持单品种和多品种模式。instrument_ids 和 bar_types 长度必须一致。

    Attributes:
        instrument_ids: 品种 ID 列表。
        bar_types: K 线类型列表。
        trade_size: 每笔交易数量。
        log_level: 日志级别。
    """

    instrument_ids: List[InstrumentId]
    bar_types: List[str]
    trade_size: Decimal = field(default_factory=lambda: Decimal("1.0"))
    log_level: str = "INFO"

    def __post_init__(self):
        if not self.instrument_ids or not self.bar_types:
            raise ValueError("instrument_ids 和 bar_types 不能为空")
        if len(self.instrument_ids) != len(self.bar_types):
            raise ValueError(
                f"instrument_ids ({len(self.instrument_ids)}) 和 "
                f"bar_types ({len(self.bar_types)}) 长度必须相同"
            )

    @property
    def instrument_id(self) -> InstrumentId:
        """获取第一个品种 ID（便捷访问）"""
        return self.instrument_ids[0]

    @property
    def bar_type(self) -> str:
        """获取第一个 K 线类型（便捷访问）"""
        return self.bar_types[0]

    @property
    def is_multi_symbol(self) -> bool:
        """是否为多品种模式"""
        return len(self.instrument_ids) > 1
