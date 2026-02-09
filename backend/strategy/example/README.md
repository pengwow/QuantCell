# QuantCell 高性能策略执行模块演示

本演示应用展示了 QuantCell 策略核心模块的高性能特性，包括多种事件引擎、批处理、内存池优化、硬件优化和弹性机制。

## 目录结构

```
backend/strategy/example/
├── README.md                    # 本文件
├── demo.py                      # 主演示脚本
├── __init__.py
├── strategies/                  # 示例策略
│   ├── __init__.py
│   ├── vectorized_sma.py       # 向量化双均线策略
│   ├── concurrent_pairs.py     # 并发多交易对策略
│   └── async_event_driven.py   # 异步事件驱动策略
├── benchmarks/                  # 性能测试
│   ├── __init__.py
│   ├── base.py                 # 基准测试基类
│   ├── engine_benchmark.py     # 引擎对比测试
│   ├── throughput_test.py      # 吞吐量测试
│   └── latency_test.py         # 延迟测试
├── tests/                       # 测试用例
│   ├── __init__.py
│   └── test_strategies.py      # 策略测试
└── docs/                        # 文档
    ├── ARCHITECTURE.md         # 架构说明
    └── USAGE.md                # 使用指南
```

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

## 演示内容

### 1. 向量化双均线策略

展示 NumPy 向量化计算的性能优势：
- 批量计算移动平均线
- 向量化信号生成
- 批量订单提交
- 向量化回测

### 2. 并发多交易对策略

展示多交易对并行处理能力：
- 交易对分片（16-64分片）
- 一致性哈希路由
- 每交易对独立队列
- 符号级并发控制

### 3. 异步事件驱动策略

展示 asyncio 高性能事件处理：
- 真正的异步事件处理
- 协程级别的并发
- 支持数千并发任务
- 更低的延迟

### 4. 引擎性能对比

对比各引擎的吞吐量和延迟：
- 基础事件引擎 (EventEngine)
- 优化事件引擎 (OptimizedEventEngine)
- 异步事件引擎 (AsyncEventEngine)
- 并发事件引擎 (ConcurrentEventEngine)

### 5. 吞吐量测试

测试各引擎在不同负载下的吞吐量表现。

### 6. 延迟测试

测试各引擎的事件处理延迟分布。

## 性能特性

| 引擎 | 吞吐量 | 延迟 | 适用场景 |
|------|--------|------|----------|
| EventEngine | 10K/s | 1-10ms | 简单场景 |
| OptimizedEventEngine | 100K/s | 0.1-1ms | 高并发 |
| AsyncEventEngine | 1M/s | 0.01-0.1ms | 超高频 |
| ConcurrentEventEngine | 100K/s | 0.1-1ms | 多交易对 |
| BatchingEngine | 500K/s | 10ms | 批量处理 |

## 运行测试

```bash
# 运行所有测试
cd /Users/liupeng/workspace/quant/QuantCell/backend
python -m pytest strategy/example/tests/ -v

# 运行特定测试
python -m pytest strategy/example/tests/test_strategies.py::TestVectorizedSMAStrategy -v
```

## 文档

- [架构说明](docs/ARCHITECTURE.md) - 详细架构设计说明
- [使用指南](docs/USAGE.md) - 详细使用说明和最佳实践

## 核心模块

本演示基于 `strategy/core` 模块，包含以下核心组件：

1. **事件引擎**
   - EventEngine: 基础事件引擎
   - OptimizedEventEngine: 优化事件引擎
   - AsyncEventEngine: 异步事件引擎
   - ConcurrentEventEngine: 并发事件引擎

2. **批处理引擎**
   - BatchingEngine: 微批处理和向量化执行

3. **内存池**
   - ObjectPool: 对象复用
   - SharedMemoryMarketData: 共享内存

4. **硬件优化器**
   - NUMAOptimizer: NUMA感知优化
   - ThreadAffinityManager: 线程亲和性管理
   - CacheOptimizer: 缓存优化

5. **弹性机制**
   - GracefulDegradation: 优雅降级
   - CircuitBreaker: 熔断器
   - AutoScaler: 自动扩缩容
   - ExceptionIsolation: 异常隔离

## 许可证

MIT License
