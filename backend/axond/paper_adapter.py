"""Paper 模式交易所适配器 — 内存行情 + 模拟撮合

仅用于 paper / testnet 模式下的策略回放，不连接真实交易所。
接口契约与 :mod:`axond.strategy_loop` 要求的 exchange adapter 一致：
``connect / disconnect / subscribe / get_ticker / place_order``。
"""
from __future__ import annotations

import random
import threading
import time
from typing import Any, Dict, List, Optional


class PaperExchangeAdapter:
    """纸面交易适配器：内存模拟行情与下单。

    特点：
        - 单线程线程安全（self._lock）
        - ticker 行情可由调用方注入，否则用随机游走生成
        - place_order 直接返回内存字典，不触发真实成交回调
    """

    def __init__(self, exchange: str = "paper", trading_mode: str = "paper") -> None:
        self._exchange = exchange
        self._trading_mode = trading_mode
        self._connected = False
        self._subscribed: List[str] = []
        self._tickers: Dict[str, Dict[str, float]] = {}
        self._orders: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def exchange(self) -> str:
        return self._exchange

    @property
    def trading_mode(self) -> str:
        return self._trading_mode

    def connect(self) -> None:
        """连接交易所（paper 模式下为空操作）。"""
        with self._lock:
            if self._connected:
                return
            self._connected = True

    def disconnect(self) -> None:
        """断开连接。"""
        with self._lock:
            self._connected = False
            self._subscribed = []

    def subscribe(self, symbols: List[str]) -> None:
        """订阅行情。paper 模式下只为 symbols 初始化一个基准价。"""
        with self._lock:
            for symbol in symbols:
                if symbol not in self._tickers:
                    self._tickers[symbol] = self._seed_ticker(symbol)
                if symbol not in self._subscribed:
                    self._subscribed.append(symbol)

    def inject_ticker(self, symbol: str, ticker: Dict[str, float]) -> None:
        """注入/覆盖指定 symbol 的行情（用于回放或测试）。"""
        with self._lock:
            self._tickers[symbol] = dict(ticker)

    def get_ticker(self, symbol: str) -> Dict[str, float]:
        """获取行情。paper 模式基于随机游走生成。"""
        with self._lock:
            if symbol not in self._tickers:
                self._tickers[symbol] = self._seed_ticker(symbol)
            t = self._tickers[symbol]
            # 随机游走 ±0.05%
            last = t["last"]
            drift = last * random.uniform(-0.0005, 0.0005)
            new_last = max(last + drift, 0.01)
            t["last"] = new_last
            t["high"] = max(t["high"], new_last)
            t["low"] = min(t["low"], new_last)
            t["volume"] += random.uniform(0, 1.0)
            return dict(t)

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """模拟下单。返回带 client_order_id 的回执字典。"""
        with self._lock:
            order_id = f"paper-{int(time.time() * 1000)}-{len(self._orders) + 1}"
            receipt = {
                "order_id": order_id,
                "client_order_id": order.get("client_order_id", order_id),
                "status": "ACCEPTED",
                "filled_qty": 0.0,
                "avg_fill_price": 0.0,
                **order,
            }
            self._orders.append(receipt)
            return receipt

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for o in self._orders:
                if o.get("order_id") == order_id:
                    return dict(o)
        return None

    def list_orders(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(o) for o in self._orders]

    @staticmethod
    def _seed_ticker(symbol: str) -> Dict[str, float]:
        # 使用 symbol 哈希作为伪随机种子，保证同一 symbol 的基准价稳定
        base = 100.0 + (hash(symbol) % 9000)
        return {
            "open": base,
            "high": base * 1.001,
            "low": base * 0.999,
            "last": base,
            "volume": 0.0,
        }


def build_paper_adapter(exchange: str = "paper", trading_mode: str = "paper") -> PaperExchangeAdapter:
    """工厂函数：构造 PaperExchangeAdapter。"""
    return PaperExchangeAdapter(exchange=exchange, trading_mode=trading_mode)


__all__ = ["PaperExchangeAdapter", "build_paper_adapter"]
