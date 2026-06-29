# -*- coding: utf-8 -*-
"""Data Service — axon_quant.data 数据服务

包装 axon_quant.data.DataService，提供数据加载、缓存、流式访问等功能。
当 axon_quant 不可用时提供清晰的错误信息。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant.data import (
        DataService as _DataService,
        DataRequest as _DataRequest,
        MockSource as _MockSource,
        Frequency as _Frequency,
        Dataset as _Dataset,
    )
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _DataService = None
    _DataRequest = None
    _MockSource = None
    _Frequency = None
    _Dataset = None


class DataServiceWrapper:
    """数据服务包装器

    包装 axon_quant.data.DataService，提供数据加载、缓存、流式访问等功能。

    Example:
        >>> svc = DataServiceWrapper(cache_capacity=64)
        >>> svc.register_mock_source("btc", 1000, 1_000_000, lambda i: 100.0 + i)
        >>> dataset = svc.load("BTCUSDT", start, end, frequency="Tick")
        >>> print(dataset.len, dataset.checksum[:8])
        >>> batch = dataset.to_arrow(0)  # zero-copy pyarrow.RecordBatch
    """

    def __init__(self, cache_capacity: int = 64):
        """初始化数据服务

        Args:
            cache_capacity: 缓存容量
        """
        if not AXON_AVAILABLE:
            raise RuntimeError(
                "axon_quant.data 不可用，请安装 axon_quant: pip install axon_quant"
            )

        self._service = _DataService.new().with_cache_capacity(cache_capacity)
        logger.info(f"DataService 已初始化: cache_capacity={cache_capacity}")

    def register_mock_source(
        self,
        name: str,
        count: int,
        nanos_per_step: int,
        price_fn: Any,
    ) -> None:
        """注册 Mock 数据源

        Args:
            name: 数据源名称
            count: 数据点数量
            nanos_per_step: 每步时间间隔（纳秒）
            price_fn: 价格函数 (index) -> price
        """
        source = _MockSource.with_tick_series(name, count, nanos_per_step, price_fn)
        self._service.register_source(source)
        logger.info(f"Mock 数据源已注册: {name}, count={count}")

    def register_source(self, source: Any) -> None:
        """注册自定义数据源

        Args:
            source: 数据源实例
        """
        self._service.register_source(source)

    def load(
        self,
        symbol: str,
        start: Any,
        end: Any,
        frequency: str = "Hour1",
    ) -> Any:
        """加载数据

        Args:
            symbol: 交易对符号
            start: 开始时间
            end: 结束时间
            frequency: 频率 ("Tick", "Min1", "Min5", "Min15", "Min30",
                       "Hour1", "Hour4", "Day1", "Week1", "Month1")

        Returns:
            Dataset 实例
        """
        # 转换频率字符串为 Frequency 枚举
        freq_map = {
            "Tick": _Frequency.Tick,
            "Min1": _Frequency.Min1,
            "Min5": _Frequency.Min5,
            "Min15": _Frequency.Min15,
            "Min30": _Frequency.Min30,
            "Hour1": _Frequency.Hour1,
            "Hour4": _Frequency.Hour4,
            "Day1": _Frequency.Day1,
            "Week1": _Frequency.Week1,
            "Month1": _Frequency.Month1,
        }
        freq = freq_map.get(frequency, _Frequency.Hour1)

        # 创建请求
        req = _DataRequest(symbol, start, end, freq)

        # 加载数据
        dataset = self._service.load(req)
        logger.info(f"数据已加载: {symbol}, len={dataset.len}")
        return dataset

    def stream(self, source_name: str, req: Any) -> Any:
        """流式加载数据

        Args:
            source_name: 数据源名称
            req: 数据请求

        Returns:
            数据流
        """
        return self._service.stream(source_name, req)

    def cache_stats(self) -> dict[str, Any]:
        """获取缓存统计

        Returns:
            缓存统计字典
        """
        return self._service.cache_stats()

    def cache_control(self) -> Any:
        """获取缓存控制器

        Returns:
            缓存控制器
        """
        return self._service.cache_control()


class DataServiceProxy:
    """数据服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self, cache_capacity: int = 64):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._service = DataServiceWrapper(cache_capacity)
            except Exception as e:
                logger.error(f"创建 DataServiceWrapper 失败: {e}")
                self._available = False
                self._service = None
        else:
            self._service = None
            logger.warning("axon_quant.data 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.data 是否可用"""
        return self._available

    def register_mock_source(
        self,
        name: str,
        count: int,
        nanos_per_step: int,
        price_fn: Any,
    ) -> None:
        """注册 Mock 数据源"""
        if self._available and self._service:
            self._service.register_mock_source(name, count, nanos_per_step, price_fn)

    def register_source(self, source: Any) -> None:
        """注册自定义数据源"""
        if self._available and self._service:
            self._service.register_source(source)

    def load(
        self,
        symbol: str,
        start: Any,
        end: Any,
        frequency: str = "Hour1",
    ) -> Optional[Any]:
        """加载数据"""
        if not self._available or not self._service:
            return None
        return self._service.load(symbol, start, end, frequency)

    def stream(self, source_name: str, req: Any) -> Optional[Any]:
        """流式加载数据"""
        if not self._available or not self._service:
            return None
        return self._service.stream(source_name, req)

    def cache_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        if not self._available or not self._service:
            return {}
        return self._service.cache_stats()

    def cache_control(self) -> Optional[Any]:
        """获取缓存控制器"""
        if not self._available or not self._service:
            return None
        return self._service.cache_control()
