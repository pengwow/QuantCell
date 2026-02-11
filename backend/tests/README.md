# QuantCell 测试运行完整指南

## 目录
1. [前置条件和环境配置](#1-前置条件和环境配置)
2. [测试文件结构](#2-测试文件结构)
3. [命令行指令](#3-命令行指令)
4. [测试结果解读](#4-测试结果解读)
5. [运行示例](#5-运行示例)
6. [故障排查](#6-故障排查)

---

## 1. 前置条件和环境配置

### 1.1 必要环境

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.12 | 项目要求 |
| uv | 最新版 | 包管理工具 |
| pytest | >= 9.0.1 | 已在 pyproject.toml 中声明 |

### 1.2 环境检查

```bash
# 进入后端目录
cd backend

# 检查Python版本
python3 --version

# 检查uv是否安装
uv --version

# 检查pytest是否可用
uv run pytest --version
```

### 1.3 安装依赖

```bash
# 首次运行，安装所有依赖
cd backend
uv sync

# 或者只安装测试相关依赖
uv add --dev pytest pytest-asyncio pytest-cov pytest-timeout
```

---

## 2. 测试文件结构

所有单元测试位于：`backend/tests/unit/`

```
tests/
├── README.md                    # 本文件
└── unit/                        # 单元测试目录
    ├── test_event_engine_optimized.py    # 优化事件引擎测试 (27+ 测试)
    ├── test_async_event_engine.py        # 异步事件引擎测试 (25+ 测试)
    ├── test_concurrent_event_engine.py   # 并发事件引擎测试 (24+ 测试)
    ├── test_batching_engine.py           # 批处理引擎测试 (26+ 测试)
    ├── test_memory_pool.py               # 内存池测试 (25+ 测试)
    ├── test_hardware_optimizer.py        # 硬件优化器测试 (24+ 测试)
    └── test_resilience.py                # 弹性机制测试 (50+ 测试)
```

**总计：约 200+ 个测试用例**

---

## 3. 命令行指令

### 3.1 基础命令

#### 运行所有测试
```bash
cd backend
uv run pytest tests/unit/ -v
```

#### 运行单个测试文件
```bash
# 弹性机制测试
cd backend
uv run pytest tests/unit/test_resilience.py -v

# 事件引擎测试
cd backend
uv run pytest tests/unit/test_event_engine_optimized.py -v
```

#### 运行特定测试类
```bash
# 优雅降级测试类
cd backend
uv run pytest tests/unit/test_resilience.py::TestGracefulDegradation -v

# 熔断器测试类
cd backend
uv run pytest tests/unit/test_resilience.py::TestCircuitBreaker -v
```

#### 运行特定测试方法
```bash
# 单个测试方法
cd backend
uv run pytest tests/unit/test_resilience.py::TestGracefulDegradation::test_initial_state -v
```

### 3.2 高级过滤

#### 按关键字过滤
```bash
# 运行包含 "degradation" 关键字的测试
cd backend
uv run pytest tests/unit/ -v -k "degradation"

# 运行包含 "circuit" 或 "breaker" 的测试
cd backend
uv run pytest tests/unit/ -v -k "circuit or breaker"

# 排除包含 "slow" 的测试
cd backend
uv run pytest tests/unit/ -v -k "not slow"
```

#### 按标记过滤
```bash
# 只运行慢速测试（性能基准测试）
cd backend
uv run pytest tests/unit/ -m slow -v

# 排除慢速测试（快速验证）
cd backend
uv run pytest tests/unit/ -m "not slow" -v
```

### 3.3 覆盖率测试

```bash
# 生成覆盖率报告（终端+HTML）
cd backend
uv run pytest tests/unit/ --cov=strategy.core --cov-report=html --cov-report=term

# 查看HTML报告
open htmlcov/index.html
```

### 3.4 常用参数速查表

| 参数 | 说明 | 使用场景 |
|------|------|---------|
| `-v` | 详细输出 | 查看每个测试的详细结果 |
| `-s` | 显示print输出 | 调试时查看日志 |
| `-x` | 遇到失败立即停止 | 快速定位问题 |
| `--tb=short` | 简短错误回溯 | 快速查看错误 |
| `--tb=long` | 详细错误回溯 | 深入分析问题 |
| `-k <keyword>` | 按关键字过滤 | 运行相关测试子集 |
| `-m <marker>` | 按标记过滤 | 运行特定类型测试 |
| `--durations=N` | 显示最慢的N个测试 | 性能分析 |
| `--collect-only` | 只收集不执行 | 查看有哪些测试 |
| `--timeout=N` | 设置超时（秒） | 防止测试卡死 |

---

## 4. 测试结果解读

### 4.1 成功输出

```
============================= test session starts =============================
platform darwin -- Python 3.12.0, pytest-9.0.1, pluggy-1.0.0
rootdir: backend
collected 350 items

tests/unit/test_resilience.py::TestGracefulDegradation::test_initial_state PASSED [ 14%]
tests/unit/test_resilience.py::TestGracefulDegradation::test_should_accept_event_normal PASSED [ 28%]
tests/unit/test_resilience.py::TestCircuitBreaker::test_initial_state PASSED [ 42%]
...

========================= 350 passed in 15.23s =========================
```

### 4.2 失败输出

```
============================= test session starts =============================
...
tests/unit/test_resilience.py::TestCircuitBreaker::test_open_after_failures FAILED [ 50%]

========================= FAILURES =========================
________________ TestCircuitBreaker.test_open_after_failures ________________

self = <test_resilience.TestCircuitBreaker object at 0x...>
    def test_open_after_failures(self, circuit_breaker):
        for _ in range(3):
            circuit_breaker.record_failure()
    
>       assert circuit_breaker.state == CircuitBreakerState.OPEN
E       AssertionError: assert <CircuitBreakerState.CLOSED: 0> == CircuitBreakerState.OPEN

...
========================= 1 failed, 349 passed in 12.34s =========================
```

### 4.3 状态说明

| 状态 | 含义 | 处理方式 |
|------|------|---------|
| **PASSED** | 测试通过 | 无需处理 |
| **FAILED** | 断言失败 | 检查代码逻辑 |
| **ERROR** | 执行错误 | 检查fixture或环境 |
| **SKIPPED** | 被跳过 | 检查跳过条件 |
| **XFAIL** | 预期失败 | 正常，已标记 |
| **XPASS** | 预期失败但通过 | 可能需要更新测试 |

---

## 5. 运行示例

### 示例1：快速验证所有测试

```bash
cd backend
uv run pytest tests/unit/ -v --tb=short
```

**预期输出：**
```
============================= test session starts =============================
platform darwin -- Python 3.12.0, pytest-9.0.1, pluggy-1.0.0
rootdir: backend
collected 350 items

tests/unit/test_event_engine_optimized.py::TestOptimizedEventEngine::test_basic_event_processing PASSED [  0%]
tests/unit/test_event_engine_optimized.py::TestOptimizedEventEngine::test_priority_ordering PASSED [  1%]
tests/unit/test_event_engine_optimized.py::TestOptimizedEventEngine::test_backpressure_mechanism PASSED [  2%]
...
tests/unit/test_resilience.py::TestGracefulDegradation::test_initial_state PASSED [ 98%]
tests/unit/test_resilience.py::TestCircuitBreaker::test_open_after_failures PASSED [ 99%]

======================== 350 passed in 15.23s =========================
```

### 示例2：只运行弹性机制相关测试

```bash
cd backend
uv run pytest tests/unit/test_resilience.py -v -k "degradation or circuit"
```

**预期输出：**
```
============================= test session starts =============================
platform darwin -- Python 3.12.0, pytest-9.0.1, pluggy-1.0.0
rootdir: backend
collected 50 items / 35 deselected / 15 selected

tests/unit/test_resilience.py::TestGracefulDegradation::test_initial_state PASSED [  7%]
tests/unit/test_resilience.py::TestGracefulDegradation::test_should_accept_event_normal PASSED [ 13%]
tests/unit/test_resilience.py::TestGracefulDegradation::test_level_upgrade_light PASSED [ 20%]
tests/unit/test_resilience.py::TestGracefulDegradation::test_auto_recovery PASSED [ 27%]
tests/unit/test_resilience.py::TestCircuitBreaker::test_initial_state PASSED [ 33%]
tests/unit/test_resilience.py::TestCircuitBreaker::test_open_after_failures PASSED [ 40%]
tests/unit/test_resilience.py::TestCircuitBreaker::test_half_open_after_timeout PASSED [ 47%]
tests/unit/test_resilience.py::TestCircuitBreaker::test_close_after_success_in_half_open PASSED [ 53%]
tests/unit/test_resilience.py::TestCircuitBreaker::test_reopen_after_failure_in_half_open PASSED [ 60%]
...

======================== 15 passed in 5.67s =========================
```

### 示例3：运行性能基准测试

```bash
cd backend
uv run pytest tests/unit/ -m slow -v --durations=10
```

**预期输出：**
```
============================= test session starts =============================
platform darwin -- Python 3.12.0, pytest-9.0.1, pluggy-1.0.0
rootdir: backend
collected 350 items / 320 deselected / 30 selected

tests/unit/test_resilience.py::TestResiliencePerformanceBenchmarks::test_graceful_degradation_performance PASSED [  3%]
优雅降级检查性能: 1,250,000 操作/秒

tests/unit/test_resilience.py::TestResiliencePerformanceBenchmarks::test_circuit_breaker_performance PASSED [  6%]
熔断器操作性能: 850,000 操作/秒

tests/unit/test_event_engine_optimized.py::TestPerformanceBenchmarks::test_throughput_benchmark PASSED [ 10%]
吞吐量: 15,000 事件/秒

tests/unit/test_event_engine_optimized.py::TestPerformanceBenchmarks::test_latency_benchmark PASSED [ 13%]
平均延迟: 12.34 ms
P99延迟: 45.67 ms
...

======================== 30 passed in 45.67s =========================

======================== slowest 10 test durations =========================
30.23s tests/unit/test_event_engine_optimized.py::TestPerformanceBenchmarks::test_throughput_benchmark
12.45s tests/unit/test_concurrent_event_engine.py::TestConcurrentPerformanceBenchmarks::test_concurrent_throughput_benchmark
8.91s tests/unit/test_batching_engine.py::TestBatchingPerformanceBenchmarks::test_batching_throughput_benchmark
...
```

### 示例4：生成并查看覆盖率报告

```bash
# 生成覆盖率报告
cd backend
uv run pytest tests/unit/ --cov=strategy.core --cov-report=html --cov-report=term

# 查看HTML报告
open htmlcov/index.html
```

**预期输出（终端部分）：**
```
============================= test session starts =============================
...

---------- coverage: platform darwin, python 3.12.0-final-0 -----------
Name                                              Stmts   Miss  Cover
---------------------------------------------------------------------
strategy/core/__init__.py                            45      0   100%
strategy/core/event_engine_optimized.py             234     12    95%
strategy/core/async_event_engine.py                 198     15    92%
strategy/core/concurrent_event_engine.py            267     23    91%
strategy/core/batching_engine.py                    245     18    93%
strategy/core/memory_pool.py                        189     14    93%
strategy/core/hardware_optimizer.py                 156     21    87%
strategy/core/resilience.py                         312     28    91%
---------------------------------------------------------------------
TOTAL                                              1646    131    92%

======================== 350 passed in 25.34s =========================
```

---

## 6. 故障排查

### 6.1 模块导入错误

**问题：** `ModuleNotFoundError: No module named 'strategy'`

**解决：**
```bash
# 确保在backend目录下运行
cd backend

# 设置PYTHONPATH
export PYTHONPATH=backend:$PYTHONPATH

# 再次运行测试
uv run pytest tests/unit/
```

### 6.2 异步测试错误

**问题：** `pytest-asyncio` 相关错误

**解决：**
```bash
# 安装pytest-asyncio
uv add --dev pytest-asyncio

# 运行异步测试
uv run pytest tests/unit/test_async_event_engine.py -v
```

### 6.3 测试超时

**问题：** 某些测试卡住不动

**解决：**
```bash
# 安装pytest-timeout
uv add --dev pytest-timeout

# 设置全局超时（每个测试最多60秒）
uv run pytest tests/unit/ --timeout=60
```

### 6.4 内存不足

**问题：** 性能测试导致内存不足

**解决：**
```bash
# 排除内存密集型测试
uv run pytest tests/unit/ -m "not slow" -v

# 或者单独运行特定测试文件
uv run pytest tests/unit/test_resilience.py -v
```

---

## 7. 快速参考卡片

### 最常用命令

```bash
# 1. 运行所有测试（快速验证）
cd backend && uv run pytest tests/unit/ -v

# 2. 运行弹性机制测试
cd backend && uv run pytest tests/unit/test_resilience.py -v

# 3. 运行特定测试方法
cd backend && uv run pytest tests/unit/test_resilience.py::TestGracefulDegradation::test_initial_state -v

# 4. 运行性能测试
cd backend && uv run pytest tests/unit/ -m slow -v

# 5. 生成覆盖率报告
cd backend && uv run pytest tests/unit/ --cov=strategy.core --cov-report=html

# 6. 快速失败模式（遇到错误立即停止）
cd backend && uv run pytest tests/unit/ -x -v

# 7. 查看测试列表（不执行）
cd backend && uv run pytest tests/unit/ --collect-only
```

---

## 8. CI/CD 配置示例

### GitHub Actions 配置

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install uv
        run: pip install uv
      
      - name: Install dependencies
        run: cd backend && uv sync
      
      - name: Run tests
        run: cd backend && uv run pytest tests/unit/ -v --tb=short
      
      - name: Run tests with coverage
        run: cd backend && uv run pytest tests/unit/ --cov=strategy.core --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./backend/coverage.xml
```

---

**最后更新：** 2025年
**维护者：** QuantCell 开发团队
