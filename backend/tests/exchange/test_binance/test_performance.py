"""
Binance模块性能测试

测试系统在高负载下的表现
"""

import time
import tracemalloc

import pytest

from exchange.binance.config import OrderSide, OrderType
from exchange.binance.paper_trading import PaperTradingAccount


class TestPerformance:
    """性能测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.account = PaperTradingAccount(
            initial_balance={"USDT": 1000000.0, "BTC": 100.0},
            maker_fee=0.001,
            taker_fee=0.001,
        )
        self.account.update_market_price("BTCUSDT", 50000.0)

    # ==================== 批量订单测试 ====================

    def test_batch_orders_100(self):
        """测试批量创建100个订单"""
        start_time = time.time()

        orders = []
        for i in range(100):
            order = self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.001,
                price=1000.0 + i,
            )
            orders.append(order)

        elapsed = time.time() - start_time

        assert len(orders) == 100
        assert elapsed < 1.0  # 应该在1秒内完成

    def test_batch_orders_1000(self):
        """测试批量创建1000个订单"""
        start_time = time.time()

        orders = []
        for i in range(1000):
            order = self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.0001,
                price=1000.0 + i,
            )
            orders.append(order)

        elapsed = time.time() - start_time

        assert len(orders) == 1000
        assert elapsed < 5.0  # 应该在5秒内完成

    @pytest.mark.slow
    def test_batch_orders_10000(self):
        """测试批量创建10000个订单（慢测试）"""
        start_time = time.time()

        orders = []
        for i in range(10000):
            order = self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.00001,
                price=1000.0 + i,
            )
            orders.append(order)

        time.time() - start_time

        assert len(orders) == 10000

    # ==================== 高频交易测试 ====================

    def test_high_frequency_trading(self):
        """测试高频交易模拟"""
        # 模拟1秒内创建多个订单
        duration = 1.0
        start_time = time.time()
        order_count = 0

        while time.time() - start_time < duration:
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.0001,
            )
            order_count += 1

        assert order_count > 100  # 至少每秒100个订单

    # ==================== 持仓管理测试 ====================

    def test_large_number_of_positions(self):
        """测试大量持仓管理"""
        symbols = [f"COIN{i}USDT" for i in range(100)]

        start_time = time.time()

        for symbol in symbols:
            self.account.update_market_price(symbol, 100.0)
            self.account.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )

        time.time() - start_time

        positions = self.account.get_all_positions()
        assert len(positions) == 100

    # ==================== 内存使用测试 ====================

    def test_memory_usage_orders(self):
        """测试订单内存使用"""
        tracemalloc.start()

        # 创建1000个订单前的内存
        snapshot1 = tracemalloc.take_snapshot()

        for i in range(1000):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.0001,
                price=1000.0 + i,
            )

        # 创建1000个订单后的内存
        snapshot2 = tracemalloc.take_snapshot()

        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_size = sum(stat.size for stat in top_stats[:5])

        # 每个订单应该占用较少内存
        avg_size = total_size / 1000
        assert avg_size < 1024  # 平均每个订单小于1KB

        tracemalloc.stop()

    def test_memory_usage_positions(self):
        """测试持仓内存使用"""
        tracemalloc.start()

        snapshot1 = tracemalloc.take_snapshot()

        # 创建100个持仓
        for i in range(100):
            symbol = f"COIN{i}USDT"
            self.account.update_market_price(symbol, 100.0)
            self.account.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )

        snapshot2 = tracemalloc.take_snapshot()

        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        sum(stat.size for stat in top_stats[:5])

        tracemalloc.stop()

    # ==================== 响应时间测试 ====================

    def test_order_creation_latency(self):
        """测试订单创建延迟"""
        latencies = []

        for _ in range(100):
            start = time.perf_counter()
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.001,
            )
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # 转换为毫秒

        avg_latency = sum(latencies) / len(latencies)
        max(latencies)
        min(latencies)

        assert avg_latency < 10  # 平均延迟小于10ms

    def test_position_query_latency(self):
        """测试持仓查询延迟"""
        # 先创建一些持仓
        for i in range(50):
            symbol = f"COIN{i}USDT"
            self.account.update_market_price(symbol, 100.0)
            self.account.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )

        # 测试查询延迟
        latencies = []

        for _ in range(100):
            start = time.perf_counter()
            self.account.get_all_positions()
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        avg_latency = sum(latencies) / len(latencies)

        assert avg_latency < 1  # 查询延迟小于1ms

    # ==================== 并发测试 ====================

    def test_concurrent_order_creation(self):
        """测试并发订单创建"""
        import threading

        orders_created = []
        errors = []

        def create_orders(count):
            try:
                for i in range(count):
                    order = self.account.create_order(
                        symbol="BTCUSDT",
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        quantity=0.0001,
                        price=1000.0 + i,
                    )
                    orders_created.append(order)
            except Exception as e:
                errors.append(e)

        start_time = time.time()

        # 创建4个线程，每个创建25个订单
        threads = []
        for _ in range(4):
            t = threading.Thread(target=create_orders, args=(25,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        time.time() - start_time

        assert len(errors) == 0
        assert len(orders_created) == 100

    # ==================== 大数据量测试 ====================

    def test_large_account_summary(self):
        """测试大量数据的账户摘要"""
        # 创建大量持仓和订单
        for i in range(100):
            symbol = f"COIN{i}USDT"
            self.account.update_market_price(symbol, 100.0)
            self.account.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )

        for i in range(500):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.0001,
                price=1000.0 + i,
            )

        start_time = time.perf_counter()
        summary = self.account.get_account_summary()
        elapsed = (time.perf_counter() - start_time) * 1000

        assert summary["position_count"] == 100
        assert elapsed < 10  # 应该在10ms内完成
