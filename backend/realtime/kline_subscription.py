# -*- coding: utf-8 -*-
"""
K线数据订阅管理模块

管理K线数据的订阅状态，维护symbol->clients映射关系，
提供订阅/取消订阅API，支持按symbol和interval路由消息。

订阅主题格式: kline:{symbol}:{interval}
示例: kline:BTCUSDT:1m, kline:ETHUSDT:5m
"""

import asyncio
import time
from typing import Dict, Set, Optional, Callable, Any, List
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger


@dataclass
class KlineSubscription:
    """K线订阅信息"""
    symbol: str
    interval: str
    client_ids: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    last_push_at: Optional[float] = None
    push_count: int = 0
    error_count: int = 0


@dataclass
class KlineMetrics:
    """K线推送监控指标"""
    total_subscriptions: int = 0
    active_connections: int = 0
    total_pushes: int = 0
    total_errors: int = 0
    avg_push_latency: float = 0.0
    push_frequency: float = 0.0  # 每秒推送次数
    symbol_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class KlineSubscriptionManager:
    """K线订阅管理器"""

    # 支持的K线周期
    SUPPORTED_INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']

    def __init__(self):
        """初始化K线订阅管理器"""
        # 订阅映射: {(symbol, interval): KlineSubscription}
        self._subscriptions: Dict[tuple, KlineSubscription] = {}

        # 客户端订阅映射: {client_id: Set[(symbol, interval)]}
        self._client_subscriptions: Dict[str, Set[tuple]] = {}

        # 推送回调函数
        self._push_callbacks: List[Callable[[str, str, Dict[str, Any]], None]] = []

        # 监控指标
        self._metrics = KlineMetrics()
        self._push_latencies: List[float] = []
        self._last_metrics_update = time.time()

        # 锁
        self._lock = asyncio.Lock()

        logger.info("KlineSubscriptionManager initialized")

    def parse_topic(self, topic: str) -> Optional[tuple]:
        """
        解析K线主题

        Args:
            topic: 主题字符串，如 "kline:BTCUSDT:1m"

        Returns:
            Optional[tuple]: (symbol, interval) 或 None
        """
        try:
            parts = topic.split(':')
            if len(parts) != 3 or parts[0] != 'kline':
                return None

            symbol = parts[1].upper()
            interval = parts[2].lower()

            if interval not in self.SUPPORTED_INTERVALS:
                logger.warning(f"Unsupported interval: {interval}")
                return None

            return (symbol, interval)
        except Exception as e:
            logger.error(f"Failed to parse topic {topic}: {e}")
            return None

    def build_topic(self, symbol: str, interval: str) -> str:
        """
        构建K线主题

        Args:
            symbol: 交易对
            interval: 周期

        Returns:
            str: 主题字符串
        """
        return f"kline:{symbol.upper()}:{interval.lower()}"

    async def subscribe(self, client_id: str, symbol: str, interval: str) -> bool:
        """
        订阅K线数据

        Args:
            client_id: 客户端ID
            symbol: 交易对
            interval: 周期

        Returns:
            bool: 订阅是否成功
        """
        async with self._lock:
            try:
                symbol = symbol.upper()
                interval = interval.lower()
                key = (symbol, interval)

                # 验证interval
                if interval not in self.SUPPORTED_INTERVALS:
                    logger.error(f"Unsupported interval: {interval}")
                    return False

                # 创建或获取订阅
                if key not in self._subscriptions:
                    self._subscriptions[key] = KlineSubscription(
                        symbol=symbol,
                        interval=interval
                    )
                    logger.info(f"Created new kline subscription: {symbol}@{interval}")

                subscription = self._subscriptions[key]

                # 添加客户端
                if client_id not in subscription.client_ids:
                    subscription.client_ids.add(client_id)
                    logger.info(f"Client {client_id} subscribed to {symbol}@{interval}")

                # 更新客户端订阅映射
                if client_id not in self._client_subscriptions:
                    self._client_subscriptions[client_id] = set()
                self._client_subscriptions[client_id].add(key)

                # 更新指标
                self._metrics.total_subscriptions = len(self._subscriptions)
                self._metrics.active_connections = len(self._client_subscriptions)

                return True

            except Exception as e:
                logger.error(f"Failed to subscribe {client_id} to {symbol}@{interval}: {e}")
                return False

    async def unsubscribe(self, client_id: str, symbol: str, interval: str) -> bool:
        """
        取消订阅K线数据

        Args:
            client_id: 客户端ID
            symbol: 交易对
            interval: 周期

        Returns:
            bool: 取消订阅是否成功
        """
        async with self._lock:
            try:
                symbol = symbol.upper()
                interval = interval.lower()
                key = (symbol, interval)

                # 从订阅中移除客户端
                if key in self._subscriptions:
                    subscription = self._subscriptions[key]
                    if client_id in subscription.client_ids:
                        subscription.client_ids.remove(client_id)
                        logger.info(f"Client {client_id} unsubscribed from {symbol}@{interval}")

                    # 如果没有客户端了，删除订阅
                    if not subscription.client_ids:
                        del self._subscriptions[key]
                        logger.info(f"Removed empty subscription: {symbol}@{interval}")

                # 从客户端订阅映射中移除
                if client_id in self._client_subscriptions:
                    self._client_subscriptions[client_id].discard(key)
                    if not self._client_subscriptions[client_id]:
                        del self._client_subscriptions[client_id]

                # 更新指标
                self._metrics.total_subscriptions = len(self._subscriptions)
                self._metrics.active_connections = len(self._client_subscriptions)

                return True

            except Exception as e:
                logger.error(f"Failed to unsubscribe {client_id} from {symbol}@{interval}: {e}")
                return False

    async def unsubscribe_all(self, client_id: str) -> bool:
        """
        取消客户端的所有K线订阅

        Args:
            client_id: 客户端ID

        Returns:
            bool: 取消订阅是否成功
        """
        async with self._lock:
            try:
                if client_id not in self._client_subscriptions:
                    return True

                # 获取客户端的所有订阅
                subscriptions = list(self._client_subscriptions[client_id])

                # 逐个取消订阅
                for key in subscriptions:
                    symbol, interval = key
                    await self.unsubscribe(client_id, symbol, interval)

                logger.info(f"Client {client_id} unsubscribed from all kline channels")
                return True

            except Exception as e:
                logger.error(f"Failed to unsubscribe all for {client_id}: {e}")
                return False

    def get_subscribed_clients(self, symbol: str, interval: str) -> Set[str]:
        """
        获取订阅了指定K线的所有客户端

        Args:
            symbol: 交易对
            interval: 周期

        Returns:
            Set[str]: 客户端ID集合
        """
        key = (symbol.upper(), interval.lower())
        if key in self._subscriptions:
            return self._subscriptions[key].client_ids.copy()
        return set()

    def get_client_subscriptions(self, client_id: str) -> List[Dict[str, str]]:
        """
        获取客户端的所有K线订阅

        Args:
            client_id: 客户端ID

        Returns:
            List[Dict[str, str]]: 订阅列表
        """
        if client_id not in self._client_subscriptions:
            return []

        return [
            {"symbol": symbol, "interval": interval}
            for symbol, interval in self._client_subscriptions[client_id]
        ]

    def get_all_subscriptions(self) -> List[Dict[str, Any]]:
        """
        获取所有K线订阅信息

        Returns:
            List[Dict[str, Any]]: 订阅信息列表
        """
        return [
            {
                "symbol": sub.symbol,
                "interval": sub.interval,
                "client_count": len(sub.client_ids),
                "clients": list(sub.client_ids),
                "created_at": sub.created_at,
                "last_push_at": sub.last_push_at,
                "push_count": sub.push_count,
                "error_count": sub.error_count
            }
            for sub in self._subscriptions.values()
        ]

    async def push_kline(self, symbol: str, interval: str, kline_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        推送K线数据到订阅的客户端

        Args:
            symbol: 交易对
            interval: 周期
            kline_data: K线数据

        Returns:
            Dict[str, Any]: 推送结果统计
        """
        start_time = time.time()
        result = {
            "success": False,
            "target_clients": 0,
            "pushed_clients": 0,
            "failed_clients": 0,
            "latency_ms": 0
        }

        try:
            # 获取目标客户端
            client_ids = self.get_subscribed_clients(symbol, interval)
            result["target_clients"] = len(client_ids)

            if not client_ids:
                logger.debug(f"No clients subscribed to {symbol}@{interval}")
                return result

            # 构建消息
            topic = self.build_topic(symbol, interval)
            message = {
                "type": "kline",
                "id": f"kline_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "topic": topic,
                "data": kline_data
            }

            # 调用推送回调
            for callback in self._push_callbacks:
                try:
                    for client_id in client_ids:
                        callback(client_id, topic, message)
                        result["pushed_clients"] += 1
                except Exception as e:
                    logger.error(f"Push callback error: {e}")
                    result["failed_clients"] += 1

            # 更新订阅统计
            key = (symbol.upper(), interval.lower())
            if key in self._subscriptions:
                sub = self._subscriptions[key]
                sub.last_push_at = time.time()
                sub.push_count += 1
                if result["failed_clients"] > 0:
                    sub.error_count += result["failed_clients"]

            # 更新指标
            latency = (time.time() - start_time) * 1000
            self._push_latencies.append(latency)
            if len(self._push_latencies) > 100:
                self._push_latencies.pop(0)
            self._metrics.avg_push_latency = sum(self._push_latencies) / len(self._push_latencies)

            result["success"] = True
            result["latency_ms"] = latency

            logger.debug(f"Pushed kline to {result['pushed_clients']} clients for {symbol}@{interval}, latency={latency:.2f}ms")

        except Exception as e:
            logger.error(f"Failed to push kline for {symbol}@{interval}: {e}")
            result["failed_clients"] = result["target_clients"]

        return result

    def register_push_callback(self, callback: Callable[[str, str, Dict[str, Any]], None]) -> None:
        """
        注册推送回调函数

        Args:
            callback: 回调函数，参数为 (client_id, topic, message)
        """
        self._push_callbacks.append(callback)
        logger.info(f"Registered push callback, total callbacks: {len(self._push_callbacks)}")

    def unregister_push_callback(self, callback: Callable[[str, str, Dict[str, Any]], None]) -> bool:
        """
        注销推送回调函数

        Args:
            callback: 回调函数

        Returns:
            bool: 注销是否成功
        """
        if callback in self._push_callbacks:
            self._push_callbacks.remove(callback)
            logger.info(f"Unregistered push callback, total callbacks: {len(self._push_callbacks)}")
            return True
        return False

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取监控指标

        Returns:
            Dict[str, Any]: 监控指标
        """
        # 计算推送频率
        now = time.time()
        time_delta = now - self._last_metrics_update
        if time_delta > 0:
            total_pushes = sum(sub.push_count for sub in self._subscriptions.values())
            self._metrics.push_frequency = (total_pushes - self._metrics.total_pushes) / time_delta
            self._metrics.total_pushes = total_pushes

        self._last_metrics_update = now

        # 按symbol统计
        symbol_stats = defaultdict(lambda: {"subscriptions": 0, "clients": set(), "push_count": 0})
        for key, sub in self._subscriptions.items():
            symbol = key[0]
            symbol_stats[symbol]["subscriptions"] += 1
            symbol_stats[symbol]["clients"].update(sub.client_ids)
            symbol_stats[symbol]["push_count"] += sub.push_count

        self._metrics.symbol_stats = {
            symbol: {
                "subscriptions": stats["subscriptions"],
                "client_count": len(stats["clients"]),
                "push_count": stats["push_count"]
            }
            for symbol, stats in symbol_stats.items()
        }

        return {
            "total_subscriptions": self._metrics.total_subscriptions,
            "active_connections": self._metrics.active_connections,
            "total_pushes": self._metrics.total_pushes,
            "avg_push_latency_ms": round(self._metrics.avg_push_latency, 2),
            "push_frequency": round(self._metrics.push_frequency, 2),
            "symbol_stats": self._metrics.symbol_stats
        }

    def is_subscribed(self, client_id: str, symbol: str, interval: str) -> bool:
        """
        检查客户端是否订阅了指定K线

        Args:
            client_id: 客户端ID
            symbol: 交易对
            interval: 周期

        Returns:
            bool: 是否已订阅
        """
        key = (symbol.upper(), interval.lower())
        if key in self._subscriptions:
            return client_id in self._subscriptions[key].client_ids
        return False

    def get_supported_intervals(self) -> List[str]:
        """
        获取支持的K线周期列表

        Returns:
            List[str]: 周期列表
        """
        return self.SUPPORTED_INTERVALS.copy()


# 全局K线订阅管理器实例
kline_subscription_manager = KlineSubscriptionManager()
