# P4: 实盘交易系统迁移

## 目标

用 axon_quant.exchange 替代 nautilus TradingNode，重写实盘策略执行系统。

## 依赖

- P1 完成（axond/types.py）

## TDD 行为清单

### 1. 交易所配置（worker/config.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 1.1 | `build_exchange_config("binance", "testnet")` 返回 Binance testnet 配置 | `tests/unit/worker/test_axon_config.py` |
| 1.2 | `build_exchange_config("okx", "testnet")` 返回 OKX testnet 配置 | `tests/unit/worker/test_axon_config.py` |
| 1.3 | `build_exchange_config("binance", "production")` 从环境变量读取 key | `tests/unit/worker/test_axon_config.py` |
| 1.4 | `build_exchange_config` 缺少环境变量时抛出 ExchangeError | `tests/unit/worker/test_axon_config.py` |
| 1.5 | `build_exchange_config` 不支持的交易所抛出 ValueError | `tests/unit/worker/test_axon_config.py` |

### 2. 实盘策略执行系统（worker/worker_system.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 2.1 | `AxonTradingSystem()` 创建后策略注册表为空 | `tests/unit/worker/test_axon_trading_system.py` |
| 2.2 | `system.create_strategy(db, config)` 创建策略并返回 worker_id | `tests/unit/worker/test_axon_trading_system.py` |
| 2.3 | `system.start_strategy(worker_id)` 启动策略（创建 adapter + 连接 + 注册策略） | `tests/unit/worker/test_axon_trading_system.py` |
| 2.4 | `system.stop_strategy(worker_id)` 停止策略（断开连接 + 清理资源） | `tests/unit/worker/test_axon_trading_system.py` |
| 2.5 | `system.delete_strategy(worker_id)` 删除策略（先停止再删除） | `tests/unit/worker/test_axon_trading_system.py` |
| 2.6 | `system.list_strategies()` 返回所有策略状态 | `tests/unit/worker/test_axon_trading_system.py` |
| 2.7 | `system.get_strategy_state(worker_id)` 返回策略运行时状态 | `tests/unit/worker/test_axon_trading_system.py` |
| 2.8 | 重复启动已运行的策略抛出 WorkerAlreadyRunningException | `tests/unit/worker/test_axon_trading_system.py` |
| 2.9 | 启动不存在的策略抛出 WorkerNotFoundException | `tests/unit/worker/test_axon_trading_system.py` |
| 2.10 | `system.shutdown()` 优雅关闭所有运行中的策略 | `tests/unit/worker/test_axon_trading_system.py` |

### 3. 策略主循环（worker/strategy_loop.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 3.1 | `StrategyLoop(adapter, strategy, symbol)` 创建策略循环 | `tests/unit/worker/test_strategy_loop.py` |
| 3.2 | `loop.start()` 启动循环，调用 strategy.on_start() | `tests/unit/worker/test_strategy_loop.py` |
| 3.3 | `loop.start()` 从 adapter 获取 ticker 并构造 Bar 调用 on_bar() | `tests/unit/worker/test_strategy_loop.py` |
| 3.4 | `loop.stop()` 停止循环，调用 strategy.on_stop() + adapter.disconnect() | `tests/unit/worker/test_strategy_loop.py` |
| 3.5 | `loop.is_running` 属性反映运行状态 | `tests/unit/worker/test_strategy_loop.py` |
| 3.6 | 循环中 adapter 异常时优雅降级（记录错误，继续运行） | `tests/unit/worker/test_strategy_loop.py` |

### 4. 事件处理器（worker/event_handler.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 4.1 | `AxonEventHandler(adapter, worker_id, callback)` 创建事件处理器 | `tests/unit/worker/test_axon_event_handler.py` |
| 4.2 | `handler.on_order_filled(order_id, price, qty)` 触发回调 | `tests/unit/worker/test_axon_event_handler.py` |
| 4.3 | `handler.on_order_rejected(order_id, reason)` 触发回调 | `tests/unit/worker/test_axon_event_handler.py` |
| 4.4 | 事件写入 WorkerLog 数据库 | `tests/unit/worker/test_axon_event_handler.py` |

### 5. 实盘交易适配器（strategy/trading_adapter.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 5.1 | `AxonTradingAdapter(strategy, adapter)` 创建适配器 | `tests/unit/strategy/test_axon_trading_adapter.py` |
| 5.2 | `adapter.on_bar(bar)` 将 axon Bar 转换为 QuantCell Bar 并调用 strategy.on_bar() | `tests/unit/strategy/test_axon_trading_adapter.py` |
| 5.3 | `adapter.buy()` 通过 adapter 提交订单到交易所 | `tests/unit/strategy/test_axon_trading_adapter.py` |
| 5.4 | `adapter.get_position()` 通过 adapter 查询持仓 | `tests/unit/strategy/test_axon_trading_adapter.py` |

## 实现步骤

### Cycle 1: 交易所配置

```
RED:   写 test_axon_config.py 1.1-1.5 → 失败
GREEN: 重写 worker/config.py → 通过
```

### Cycle 2: 策略主循环

```
RED:   写 test_strategy_loop.py 3.1-3.3 → 失败
GREEN: 创建 worker/strategy_loop.py → 通过
RED:   写 test_strategy_loop.py 3.4-3.6 → 失败
GREEN: 实现 stop + is_running + 异常处理 → 通过
```

### Cycle 3: 事件处理器

```
RED:   写 test_axon_event_handler.py 4.1-4.4 → 失败
GREEN: 重写 worker/event_handler.py → 通过
```

### Cycle 4: 实盘交易适配器

```
RED:   写 test_axon_trading_adapter.py 5.1-5.4 → 失败
GREEN: 重写 strategy/trading_adapter.py → 通过
```

### Cycle 5: 实盘策略执行系统

```
RED:   写 test_axon_trading_system.py 2.1-2.5 → 失败
GREEN: 重写 worker/worker_system.py → 通过
RED:   写 test_axon_trading_system.py 2.6-2.10 → 失败
GREEN: 实现查询/状态/关闭 → 通过
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `backend/worker/config.py` | 重写：axon ExchangeConfig |
| `backend/worker/worker_system.py` | 重写：axon 实盘系统 |
| `backend/worker/strategy_loop.py` | 新建：策略主循环 |
| `backend/worker/event_handler.py` | 重写：axon 事件回调 |
| `backend/strategy/trading_adapter.py` | 重写：axon 实盘适配 |
| `backend/tests/unit/worker/test_axon_config.py` | 新建：配置测试 |
| `backend/tests/unit/worker/test_axon_trading_system.py` | 新建：系统测试 |
| `backend/tests/unit/worker/test_strategy_loop.py` | 新建：循环测试 |
| `backend/tests/unit/worker/test_axon_event_handler.py` | 新建：事件测试 |
| `backend/tests/unit/strategy/test_axon_trading_adapter.py` | 新建：适配器测试 |

## 验证

```bash
cd backend
python -m pytest tests/unit/worker/ tests/unit/strategy/ -v
```
