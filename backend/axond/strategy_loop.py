# -*- coding: utf-8 -*-
"""实盘策略主循环"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional


class StrategyLoop:
    """实盘策略主循环。

    在独立线程中运行策略，从交易所适配器获取数据并调用策略的 on_bar。

    Args:
        adapter: 交易所适配器（需实现 connect/disconnect/subscribe/get_ticker）。
        strategy: 策略实例（需实现 on_start/on_bar/on_stop）。
        symbol: 交易对符号。
        interval: 轮询间隔（秒）。
    """

    def __init__(
        self,
        adapter: Any,
        strategy: Any,
        symbol: str,
        interval: float = 1.0,
    ):
        self.adapter = adapter
        self.strategy = strategy
        self.symbol = symbol
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        """是否正在运行。"""
        return self._running

    def start(self) -> None:
        """启动策略循环。"""
        if self._running:
            return

        self.adapter.connect()
        self.adapter.subscribe([self.symbol])
        self.strategy.on_start()
        self._running = True

        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"strategy-loop-{self.symbol}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """停止策略循环。"""
        if not self._running:
            return

        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        self.strategy.on_stop()
        self.adapter.disconnect()

    def _run_loop(self) -> None:
        """策略主循环（在线程中运行）。"""
        while self._running:
            try:
                ticker = self.adapter.get_ticker(self.symbol)
                if ticker:
                    # 构造 Bar 并调用 on_bar
                    from axond.types import Bar, InstrumentId
                    from datetime import datetime, timezone
                    bar = Bar(
                        instrument_id=InstrumentId(self.symbol, "LIVE"),
                        bar_type="TICKER",
                        open=ticker.get("open", 0.0),
                        high=ticker.get("high", 0.0),
                        low=ticker.get("low", 0.0),
                        close=ticker.get("last", ticker.get("close", 0.0)),
                        volume=ticker.get("volume", 0.0),
                        timestamp=datetime.now(timezone.utc),
                        ts_event=int(time.time() * 1_000_000_000),
                    )
                    self.strategy.on_bar(bar)
            except Exception as e:
                # 策略异常不应停止循环
                pass

            time.sleep(self.interval)
