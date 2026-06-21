# P3: 策略框架重构

## 目标

重构 QuantCell 策略基类，完全脱离 nautilus Strategy，建立基于 axond.types 的新策略体系。

## 依赖

- P1 完成（axond/types.py）
- P2 完成（axon_engine.py）

## TDD 行为清单

### 1. 策略基类（backtest/strategies/base.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 1.1 | `AxonStrategy(config)` 创建后 config 正确存储 | `tests/unit/backtest/test_axon_strategy.py` |
| 1.2 | `strategy.on_start()` 设置 start_time，bars_processed=0 | `tests/unit/backtest/test_axon_strategy.py` |
| 1.3 | `strategy.on_bar(bar)` 递增 bars_processed 计数 | `tests/unit/backtest/test_axon_strategy.py` |
| 1.4 | `strategy.on_stop()` 设置 end_time | `tests/unit/backtest/test_axon_strategy.py` |
| 1.5 | `strategy.buy(symbol, quantity, price, order_type)` 创建 Buy 订单并推入引擎 | `tests/unit/backtest/test_axon_strategy.py` |
| 1.6 | `strategy.sell(symbol, quantity, price, order_type)` 创建 Sell 订单并推入引擎 | `tests/unit/backtest/test_axon_strategy.py` |
| 1.7 | `strategy.buy()` 无 price 时创建市价单（type=market） | `tests/unit/backtest/test_axon_strategy.py` |
| 1.8 | `strategy.buy()` 有限价时创建限价单（type=limit） | `tests/unit/backtest/test_axon_strategy.py` |
| 1.9 | `strategy.get_position(symbol)` 返回当前持仓 | `tests/unit/backtest/test_axon_strategy.py` |
| 1.10 | `strategy.get_position_size(symbol)` 返回持仓数量（无持仓返回 0） | `tests/unit/backtest/test_axon_strategy.py` |
| 1.11 | `strategy.close_position(symbol)` 平仓（发送反向订单） | `tests/unit/backtest/test_axon_strategy.py` |
| 1.12 | 子类实现 `on_bar()` 时可通过 `self.buy()`/`self.sell()` 下单 | `tests/unit/backtest/test_axon_strategy.py` |

### 2. 策略配置（axond/strategy_config.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 2.1 | `StrategyConfig(dataclass)` 支持 instrument_ids + bar_types 列表 | `tests/unit/axond/test_strategy_config.py` |
| 2.2 | `StrategyConfig.instrument_id` 属性返回第一个 instrument_id | `tests/unit/axond/test_strategy_config.py` |
| 2.3 | `StrategyConfig.bar_type` 属性返回第一个 bar_type | `tests/unit/axond/test_strategy_config.py` |
| 2.4 | `StrategyConfig.is_multi_symbol` 属性判断多品种模式 | `tests/unit/axond/test_strategy_config.py` |
| 2.5 | `StrategyConfig` 验证 instrument_ids 和 bar_types 长度一致 | `tests/unit/axond/test_strategy_config.py` |
| 2.6 | `StrategyConfig` 验证 instrument_ids 和 bar_types 非空 | `tests/unit/axond/test_strategy_config.py` |

### 3. 事件驱动策略（backtest/strategies/event_strategy.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 3.1 | `EventDrivenStrategy(config)` 创建后可使用 buy/sell/get_position | `tests/unit/backtest/test_event_strategy.py` |
| 3.2 | `EventDrivenStrategy` 子类实现 `_on_bar_impl(bar)` 被正确调用 | `tests/unit/backtest/test_event_strategy.py` |
| 3.3 | `EventDrivenStrategy` 支持多品种（通过 config.instrument_ids） | `tests/unit/backtest/test_event_strategy.py` |
| 3.4 | `EventDrivenStrategy` 可注入引擎（strategy._engine = axon_engine） | `tests/unit/backtest/test_event_strategy.py` |

### 4. 策略加载器（backtest/strategy_loader_service.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 4.1 | `StrategyLoaderService.load_strategy(name, params)` 加载继承 AxonStrategy 的策略 | `tests/unit/backtest/test_strategy_loader.py` |
| 4.2 | `StrategyLoaderService.load_strategy` 不存在的策略抛出 StrategyLoadError | `tests/unit/backtest/test_strategy_loader.py` |
| 4.3 | `StrategyLoaderService.load_event_strategy_multi()` 加载多品种策略 | `tests/unit/backtest/test_strategy_loader.py` |
| 4.4 | `StrategyLoaderService.load_event_strategy_multi()` 检测 AxonStrategy 子类 | `tests/unit/backtest/test_strategy_loader.py` |
| 4.5 | `StrategyLoaderService.load_event_strategy_multi()` 检测 StrategyBase 子类并适配 | `tests/unit/backtest/test_strategy_loader.py` |

### 5. 结果格式化（backtest/result_formatter_service.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 5.1 | `ResultFormatterService.format_event_results()` 单品种结果格式化 | `tests/unit/backtest/test_result_formatter.py` |
| 5.2 | `ResultFormatterService.format_event_results_multi()` 多品种结果格式化 | `tests/unit/backtest/test_result_formatter.py` |
| 5.3 | 结果包含 metrics/trades/positions/equity_curve | `tests/unit/backtest/test_result_formatter.py` |

## 实现步骤

### Cycle 1: 策略配置

```
RED:   写 test_strategy_config.py 2.1-2.6 → 失败
GREEN: 创建 axond/strategy_config.py，实现 StrategyConfig → 通过
```

### Cycle 2: 策略基类

```
RED:   写 test_axon_strategy.py 1.1-1.4 → 失败
GREEN: 重写 backtest/strategies/base.py，实现 AxonStrategy 基础生命周期 → 通过
RED:   写 test_axon_strategy.py 1.5-1.8 → 失败
GREEN: 实现 buy/sell 下单逻辑 → 通过
RED:   写 test_axon_strategy.py 1.9-1.12 → 失败
GREEN: 实现 get_position/get_position_size/close_position → 通过
```

### Cycle 3: 事件驱动策略

```
RED:   写 test_event_strategy.py 3.1-3.4 → 失败
GREEN: 重写 backtest/strategies/event_strategy.py → 通过
```

### Cycle 4: 策略加载器

```
RED:   写 test_strategy_loader.py 4.1-4.5 → 失败
GREEN: 重写 backtest/strategy_loader_service.py → 通过
```

### Cycle 5: 结果格式化

```
RED:   写 test_result_formatter.py 5.1-5.3 → 失败
GREEN: 重写 backtest/result_formatter_service.py → 通过
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `backend/axond/strategy_config.py` | 新建：策略配置基类 |
| `backend/backtest/strategies/base.py` | 重写：AxonStrategy 基类 |
| `backend/backtest/strategies/event_strategy.py` | 重写：事件驱动策略 |
| `backend/backtest/strategy_loader_service.py` | 重写：策略加载器 |
| `backend/backtest/result_formatter_service.py` | 重写：结果格式化 |
| `backend/tests/unit/backtest/test_axon_strategy.py` | 新建：策略基类测试 |
| `backend/tests/unit/axond/test_strategy_config.py` | 新建：配置测试 |
| `backend/tests/unit/backtest/test_event_strategy.py` | 新建：事件策略测试 |
| `backend/tests/unit/backtest/test_strategy_loader.py` | 新建：加载器测试 |
| `backend/tests/unit/backtest/test_result_formatter.py` | 新建：格式化测试 |

## 验证

```bash
cd backend
python -m pytest tests/unit/backtest/ tests/unit/axond/ -v
```
