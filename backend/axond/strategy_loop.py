import threading
import time
import logging
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar

logger = logging.getLogger(__name__)


class StrategyLoop:
    def __init__(self, adapter, strategy: UnifiedStrategy, symbol: str, interval: float = 1.0):
        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._interval = interval
        self._running = False
        self._thread = None
        self._ctx = StrategyContext()

    def start(self):
        self._adapter.connect()
        self._strategy.on_start(self._ctx)
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"StrategyLoop started for {self._symbol}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._strategy.on_stop(self._ctx)
        self._adapter.disconnect()
        logger.info(f"StrategyLoop stopped for {self._symbol}")

    def _run_loop(self):
        while self._running:
            try:
                ticker = self._adapter.get_ticker(self._symbol)
                bar = Bar(
                    timestamp=int(time.time() * 1_000_000_000),
                    open=ticker.get("open", 0.0),
                    high=ticker.get("high", 0.0),
                    low=ticker.get("low", 0.0),
                    close=ticker.get("last", 0.0),
                    volume=ticker.get("volume", 0.0),
                    symbol=self._symbol,
                )
                orders = self._strategy.on_bar(bar, self._ctx)
                # TODO: execute orders via adapter
            except Exception as e:
                logger.error(f"StrategyLoop error: {e}", exc_info=True)
            time.sleep(self._interval)
