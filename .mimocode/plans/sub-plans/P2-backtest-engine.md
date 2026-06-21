# P2: 回测引擎迁移

## 目标

用 axon_quant.BacktestEngine 替代 nautilus BacktestEngine，重写回测引擎核心模块，同时保持 QuantCell 的配置接口。

## 依赖

- P1 完成（axond/types.py + axond/data_converter.py）

## TDD 行为清单

### 1. 单品种回测引擎（backtest/engines/axon_engine.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 1.1 | `AxonBacktestEngine(config)` 创建时传入 initial_capital，引擎初始化成功 | `tests/unit/backtest/test_axon_engine.py` |
| 1.2 | `engine.initialize()` 创建底层 axon BacktestEngine 实例 | `tests/unit/backtest/test_axon_engine.py` |
| 1.3 | `engine.add_data(df, symbol)` 将 DataFrame 转换为事件并添加到引擎 | `tests/unit/backtest/test_axon_engine.py` |
| 1.4 | `engine.add_data` 累积数据（多次调用不覆盖） | `tests/unit/backtest/test_axon_engine.py` |
| 1.5 | `engine.submit_order(order_dict, timestamp_ns)` 推入订单事件 | `tests/unit/backtest/test_axon_engine.py` |
| 1.6 | `engine.run()` 执行回测并返回结果字典（含 final_nav, total_pnl, max_drawdown） | `tests/unit/backtest/test_axon_engine.py` |
| 1.7 | `engine.run()` 多次调用幂等（不重复消费事件） | `tests/unit/backtest/test_axon_engine.py` |
| 1.8 | `engine.cleanup()` 释放资源 | `tests/unit/backtest/test_axon_engine.py` |

### 2. 多品种回测编排器（axond/backtest_runner.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 2.1 | `MultiSymbolBacktestRunner(config)` 创建多品种回测编排器 | `tests/unit/axond/test_backtest_runner.py` |
| 2.2 | `runner.add_symbol(symbol, df)` 为每个品种创建独立的 AxonBacktestEngine | `tests/unit/axond/test_backtest_runner.py` |
| 2.3 | `runner.run()` 并行执行所有品种的回测 | `tests/unit/axond/test_backtest_runner.py` |
| 2.4 | `runner.run()` 返回汇总结果（包含每个品种的结果 + 组合指标） | `tests/unit/axond/test_backtest_runner.py` |
| 2.5 | `runner.run()` 处理部分品种失败（不影响其他品种） | `tests/unit/axond/test_backtest_runner.py` |
| 2.6 | `runner.get_results()` 返回每个品种的独立结果 | `tests/unit/axond/test_backtest_runner.py` |
| 2.7 | `runner.get_portfolio_result()` 返回组合级别的 PnL/回撤 | `tests/unit/axond/test_backtest_runner.py` |

### 3. 回测服务（backtest/engine_service.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 3.1 | `EventDrivenBacktestService(provider).run_backtest()` 执行完整回测流程 | `tests/unit/backtest/test_engine_service.py` |
| 3.2 | 回测流程：数据加载 → 引擎初始化 → 数据加载到引擎 → 策略加载 → 执行 → 结果格式化 | `tests/unit/backtest/test_engine_service.py` |
| 3.3 | 回测失败时抛出有意义的异常（数据为空、策略不存在等） | `tests/unit/backtest/test_engine_service.py` |

### 4. 数据适配器（backtest/adapters/axon_data_adapter.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 4.1 | `AxonDataAdapter.load_bars_from_csv(path)` 从 CSV 加载 OHLCV 数据 | `tests/unit/backtest/test_axon_data_adapter.py` |
| 4.2 | `AxonDataAdapter.load_bars_from_parquet(path)` 从 Parquet 加载数据 | `tests/unit/backtest/test_axon_data_adapter.py` |
| 4.3 | `AxonDataAdapter.load_multiple(symbols, timeframes)` 加载多品种多周期数据 | `tests/unit/backtest/test_axon_data_adapter.py` |
| 4.4 | `AxonDataAdapter` 加载的数据可直接传入 AxonBacktestEngine.add_data() | `tests/unit/backtest/test_axon_data_adapter.py` |
| 4.5 | `AxonDataAdapter` 处理列名标准化（大小写、日期列） | `tests/unit/backtest/test_axon_data_adapter.py` |

## 实现步骤

### Cycle 1: 单品种回测引擎

```
RED:   写 test_axon_engine.py 1.1-1.2 → 失败
GREEN: 创建 backtest/engines/axon_engine.py，实现 initialize() → 通过
RED:   写 test_axon_engine.py 1.3-1.4 → 失败
GREEN: 实现 add_data() → 通过
RED:   写 test_axon_engine.py 1.5-1.7 → 失败
GREEN: 实现 submit_order() + run() → 通过
RED:   写 test_axon_engine.py 1.8 → 失败
GREEN: 实现 cleanup() → 通过
```

### Cycle 2: 多品种编排器

```
RED:   写 test_backtest_runner.py 2.1-2.3 → 失败
GREEN: 创建 axond/backtest_runner.py，实现 add_symbol() + run() → 通过
RED:   写 test_backtest_runner.py 2.4-2.7 → 失败
GREEN: 实现结果汇总 + 错误处理 → 通过
```

### Cycle 3: 数据适配器

```
RED:   写 test_axon_data_adapter.py 4.1-4.2 → 失败
GREEN: 创建 backtest/adapters/axon_data_adapter.py，实现 CSV/Parquet 加载 → 通过
RED:   写 test_axon_data_adapter.py 4.3-4.5 → 失败
GREEN: 实现多品种加载 + 列标准化 → 通过
```

### Cycle 4: 回测服务

```
RED:   写 test_engine_service.py 3.1-3.3 → 失败
GREEN: 重写 backtest/engine_service.py → 通过
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `backend/backtest/engines/axon_engine.py` | 新建：基于 axon 的回测引擎 |
| `backend/axond/backtest_runner.py` | 新建：多品种回测编排器 |
| `backend/backtest/adapters/axon_data_adapter.py` | 新建：axon 数据适配器 |
| `backend/backtest/engine_service.py` | 重写：删除 nautilus 调用 |
| `backend/tests/unit/backtest/test_axon_engine.py` | 新建：引擎测试 |
| `backend/tests/unit/axond/test_backtest_runner.py` | 新建：编排器测试 |
| `backend/tests/unit/backtest/test_axon_data_adapter.py` | 新建：适配器测试 |
| `backend/tests/unit/backtest/test_engine_service.py` | 新建：服务测试 |

## 验证

```bash
cd backend
python -m pytest tests/unit/backtest/ tests/unit/axond/ -v
```
