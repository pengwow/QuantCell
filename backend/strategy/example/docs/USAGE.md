# 使用指南

## 快速开始

### 1. 安装依赖

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv pip install -e .
```

### 2. 运行演示

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend/strategy/example
python demo.py
```

## 示例策略使用

### 向量化双均线策略

```python
from strategy.example.strategies import VectorizedSMAStrategy
import numpy as np

# 创建策略
strategy = VectorizedSMAStrategy(
    fast_period=10,
    slow_period=30,
    batch_size=100,
)

# 启动策略
strategy.start()

# 处理K线数据
for price in prices:
    bar = {"close": price, "volume": 1000}
    signal = strategy.on_bar("BTCUSDT", bar)
    if signal:
        print(f"信号: {signal.direction} @ {signal.price}")

# 停止策略
strategy.stop()

# 获取统计
stats = strategy.get_stats()
print(f"处理K线: {stats['total_bars']}")
print(f"生成信号: {stats['signals_generated']}")
```

### 并发多交易对策略

```python
from strategy.example.strategies import ConcurrentPairsStrategy

# 创建策略
symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT"]
strategy = ConcurrentPairsStrategy(
    symbols=symbols,
    num_shards=16,
)

# 启动策略
strategy.start()

# 处理Tick数据
strategy.on_tick("BTCUSDT", price=50000.0, volume=1.5)
strategy.on_tick("ETHUSDT", price=3000.0, volume=10.0)

# 模拟市场数据
results = strategy.simulate_market_data(
    duration_seconds=10.0,
    tick_rate=100.0,
)

# 停止策略
strategy.stop()

# 查看分片分布
distribution = strategy.get_shard_distribution()
for symbol, shard_id in distribution.items():
    print(f"{symbol} -> 分片 {shard_id}")
```

### 异步事件驱动策略

```python
from strategy.example.strategies import AsyncEventDrivenStrategy
import asyncio

async def main():
    # 创建策略
    symbols = ["BTCUSDT", "ETHUSDT"]
    strategy = AsyncEventDrivenStrategy(
        symbols=symbols,
        num_workers=8,
    )

    # 启动策略
    await strategy.start()

    # 提交事件
    await strategy.submit_event(
        event_type="tick",
        symbol="BTCUSDT",
        data={"price": 50000.0, "volume": 1.5},
    )

    # 模拟高频数据
    results = await strategy.simulate_high_frequency_data(
        duration_seconds=5.0,
        events_per_second=10000,
    )

    # 停止策略
    await strategy.stop()

    print(f"事件数: {results['total_events']}")
    print(f"吞吐量: {results['events_per_second']:.0f} events/s")
    print(f"平均延迟: {results['avg_latency_ms']:.3f} ms")

# 运行
asyncio.run(main())
```

## 性能测试

### 引擎对比测试

```python
from strategy.example.benchmarks import EngineBenchmark

# 创建基准测试
benchmark = EngineBenchmark(num_events=100000)

# 执行测试
results = benchmark.execute()

# 打印对比表格
print(benchmark.get_comparison_table())
```

### 吞吐量测试

```python
from strategy.example.benchmarks import ThroughputTest

# 创建测试
test = ThroughputTest()

# 执行测试
results = test.execute()

# 获取图表数据
chart_data = test.get_throughput_chart_data()
```

### 延迟测试

```python
from strategy.example.benchmarks import LatencyTest

# 创建测试
test = LatencyTest()

# 执行测试
results = test.execute()

# 打印对比表格
print(test.get_latency_comparison_table())
```

## 高级用法

### 自定义批处理策略

```python
from strategy.core import create_batching_engine

# 创建批处理引擎
engine = create_batching_engine(
    max_batch_size=100,
    max_batch_age_ms=10.0,
    num_workers=4,
)

# 注册处理器
def process_batch(batch):
    print(f"处理批次: {len(batch)} 个事件")
    for event in batch:
        # 处理每个事件
        pass

engine.register("tick", process_batch)

# 启动引擎
engine.start()

# 添加事件
engine.put("tick", {"price": 100.0}, symbol="BTCUSDT")

# 停止引擎
engine.stop()
```

### 内存池使用

```python
from strategy.core import get_event_pools, create_tick_event

# 获取全局对象池
pools = get_event_pools()

# 获取Tick事件对象（从池中）
tick = pools.acquire_tick()
tick.set_data(
    symbol="BTCUSDT",
    price=50000.0,
    volume=1.5,
    timestamp=time.time(),
)

# 使用完毕后释放回池
tick.release()

# 或使用便捷函数（自动管理）
tick = create_tick_event(
    symbol="BTCUSDT",
    price=50000.0,
    volume=1.5,
    timestamp=time.time(),
)
# 使用 tick...
tick.release()
```

### 硬件优化

```python
from strategy.core import (
    create_numa_optimizer,
    create_thread_affinity_manager,
    pin_current_thread_to_core,
)

# 创建NUMA优化器
numa = create_numa_optimizer()

# 获取硬件信息
stats = numa.get_stats()
print(f"CPU核心数: {stats['cpu_count']}")
print(f"NUMA节点数: {stats['numa_nodes']}")

# 绑定当前线程到核心
pin_current_thread_to_core(0)

# 创建线程亲和性管理器
affinity_manager = create_thread_affinity_manager(numa)

# 为交易对分配核心
core_id = affinity_manager.register_thread(
    thread_id=threading.current_thread().ident,
    symbol="BTCUSDT",
)
print(f"BTCUSDT 分配到核心 {core_id}")
```

## 最佳实践

### 1. 选择合适的引擎

- **低并发场景**: 使用 EventEngine
- **高并发场景**: 使用 OptimizedEventEngine
- **超高频场景**: 使用 AsyncEventEngine
- **多交易对场景**: 使用 ConcurrentEventEngine
- **批量处理**: 使用 BatchingEngine

### 2. 内存优化

- 使用对象池复用事件对象
- 预分配缓冲区避免运行时分配
- 使用 `__slots__` 减少内存占用

### 3. 性能监控

- 定期检查引擎统计信息
- 监控延迟分布（P50, P90, P99）
- 关注队列使用率，避免过载

### 4. 弹性配置

- 启用优雅降级机制
- 配置合适的背压阈值
- 设置熔断器保护关键路径

## 故障排除

### 队列溢出

```python
# 增加队列大小
engine = OptimizedEventEngine(max_queue_size=500000)

# 或启用背压机制
engine = OptimizedEventEngine(
    enable_backpressure=True,
    backpressure_threshold=0.8,
)
```

### 处理延迟高

```python
# 增加工作线程数
engine = OptimizedEventEngine(num_workers=8)

# 或使用异步引擎
engine = create_async_engine(num_workers=16)
```

### 内存使用高

```python
# 使用对象池
from strategy.core import get_event_pools
pools = get_event_pools()

# 检查池统计
stats = pools.get_stats()
print(f"Tick池使用率: {stats['tick_pool']['utilization']:.2%}")
```
