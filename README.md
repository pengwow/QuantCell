# QuantCell

## 快速开始

### 后端

```bash
cd backend
uv sync
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
bun install
bun run dev
```

## 回测引擎

QuantCell 支持多种回测引擎，以满足不同场景下的回测需求。

### trading engine 引擎（默认）

[trading engine](https://trading engine.io/) 是一个高性能的量化交易平台，提供以下特性：

- **事件驱动架构**：精确模拟真实交易环境，支持复杂的订单类型和撮合逻辑
- **高性能**：基于 Rust 核心，处理速度极快，支持大规模数据回测
- **多品种支持**：可同时回测多个交易品种，支持跨品种策略
- **精细的撮合模拟**：支持限价单、止损单等多种订单类型
- **实时数据支持**：可无缝切换到实盘交易模式

### Legacy 引擎（传统引擎）

基于 backtesting.py 的传统回测引擎，作为兼容性备选方案：

- **简单易用**：API 简洁，适合快速策略原型验证
- **轻量级**：依赖少，启动速度快
- **向后兼容**：支持旧版策略代码

## 引擎切换

### 配置方式

在创建回测任务时，通过 `engine_type` 参数指定使用的引擎：

```python
# 使用 trading engine 引擎（默认）
backtest_config = {
    "symbols": ["BTCUSDT"],
    "interval": "1h",
    "start_time": "2023-01-01",
    "end_time": "2023-12-31",
    "initial_cash": 100000,
    "commission": 0.001,
    "engine_type": "advanced"  # 默认引擎
}

# 使用传统引擎
backtest_config = {
    "symbols": ["BTCUSDT"],
    "interval": "1h",
    "start_time": "2023-01-01",
    "end_time": "2023-12-31",
    "initial_cash": 100000,
    "commission": 0.001,
    "engine_type": "legacy"  # 传统引擎
}
```

### 引擎配置

引擎配置位于 `backend/backtest/config/settings.py`：

```python
from backtest.config import EngineType, DEFAULT_ENGINE

# 查看默认引擎
print(DEFAULT_ENGINE)  # EngineType.advanced

# 引擎类型枚举
EngineType.advanced  # "advanced"
EngineType.LEGACY    # "legacy"
```

## 性能对比

基于标准测试数据集的性能对比（10万条 K 线记录）：

| 指标 | trading engine 引擎 | Legacy 引擎 | 提升倍数 |
|------|---------------------|-------------|----------|
| 初始化时间 | ~0.5s | ~0.3s | 0.6x |
| 回测执行时间 | ~2.1s | ~8.5s | **4.0x** |
| 内存使用 | ~150MB | ~380MB | **2.5x** |
| 吞吐量 (records/s) | ~47,619 | ~11,765 | **4.0x** |
| 多品种支持 | 原生支持 | 需额外实现 | - |

### 适用场景建议

| 场景 | 推荐引擎 | 原因 |
|------|----------|------|
| 大规模数据回测 | trading engine | 更高的处理速度和更低的内存占用 |
| 多品种策略回测 | trading engine | 原生支持多品种并行回测 |
| 复杂订单类型 | trading engine | 支持限价单、止损单等复杂订单 |
| 快速原型验证 | Legacy | 启动快，配置简单 |
| 旧策略兼容 | Legacy | 无需修改即可运行旧版策略 |

## 插件开发指南

详细的插件开发文档请参考：[QuantCell 插件开发指南](docs/plugin.md)
