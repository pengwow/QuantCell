"""
Binance模块性能测试

测试系统在高负载下的表现
"""

import pytest
import time
import tracemalloc
from typing import List
from exchange.binance.paper_trading import PaperTradingAccount, PaperOrder
from exchange.binance.config import OrderSide, OrderType


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
        print(f"\n100 orders created in {elapsed:.4f}s ({100/elapsed:.0f} orders/sec)")
    
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
        print(f"\n1000 orders created in {elapsed:.4f}s ({1000/elapsed:.0f} orders/sec)")
    
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
        
        elapsed = time.time() - start_time
        
        assert len(orders) == 10000
        print(f"\n10000 orders created in {elapsed:.4f}s ({10000/elapsed:.0f} orders/sec)")
    
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
        
        print(f"\nHigh frequency: {order_count} orders in 1 second")
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
        
        elapsed = time.time() - start_time
        
        positions = self.account.get_all_positions()
        assert len(positions) == 100
        print(f"\n100 positions created in {elapsed:.4f}s")
    
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
        
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        total_size = sum(stat.size for stat in top_stats[:5])
        
        print(f"\nMemory used for 1000 orders: {total_size / 1024:.2f} KB")
        
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
        
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        total_size = sum(stat.size for stat in top_stats[:5])
        
        print(f"\nMemory used for 100 positions: {total_size / 1024:.2f} KB")
        
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
        max_latency = max(latencies)
        min_latency = min(latencies)
        
        print(f"\nOrder creation latency:")
        print(f"  Average: {avg_latency:.3f}ms")
        print(f"  Min: {min_latency:.3f}ms")
        print(f"  Max: {max_latency:.3f}ms")
        
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
        print(f"\nPosition query latency: {avg_latency:.3f}ms")
        
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
        
        elapsed = time.time() - start_time
        
        print(f"\nConcurrent order creation: {len(orders_created)} orders in {elapsed:.4f}s")
        
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
        
        print(f"\nAccount summary with 100 positions and 500 orders: {elapsed:.3f}ms")
        
        assert summary["position_count"] == 100
        assert elapsed < 10  # 应该在10ms内完成
