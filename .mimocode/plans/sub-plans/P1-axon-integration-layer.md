# P1: axon 集成层（类型定义 + 数据转换）

## 目标

创建 `backend/axond/` 包，定义 QuantCell 统一类型系统和 DataFrame↔axon 事件转换器，为后续所有迁移奠定基础。

## TDD 行为清单

按优先级排序，每个行为对应一个测试用例：

### 1. 类型定义（axond/types.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 1.1 | `OrderSide` 枚举值 BUY/SELL 正确映射到字符串 "Buy"/"Sell" | `tests/unit/axond/test_types.py` |
| 1.2 | `OrderType` 枚举值 MARKET/LIMIT/STOP_LOSS/STOP_LIMIT 正确映射 | `tests/unit/axond/test_types.py` |
| 1.3 | `TimeInForce` 枚举值 GTC/IOC/FOK 正确映射 | `tests/unit/axond/test_types.py` |
| 1.4 | `PositionSide` 枚举值 LONG/SHORT/FLAT 正确映射 | `tests/unit/axond/test_types.py` |
| 1.5 | `InstrumentId` 创建时 symbol+venue 正确存储，`__str__` 返回 "SYMBOL.VENUE" 格式 | `tests/unit/axond/test_types.py` |
| 1.6 | `InstrumentId` 相同 symbol+venue 的两个实例相等且可哈希（用于 dict key） | `tests/unit/axond/test_types.py` |
| 1.7 | `Bar` dataclass 创建后所有字段可访问，支持 OHLCV + timestamp + ts_event | `tests/unit/axond/test_types.py` |
| 1.8 | `QuoteTick` dataclass 包含 bid/ask/bid_size/ask_size | `tests/unit/axond/test_types.py` |
| 1.9 | `TradeTick` dataclass 包含 price/quantity/aggressor_side/trade_id | `tests/unit/axond/test_types.py` |
| 1.10 | `Position` dataclass 包含 instrument_id/side/quantity/avg_price/pnl | `tests/unit/axond/test_types.py` |
| 1.11 | `AccountBalance` dataclass 包含 currency/total/available/locked | `tests/unit/axond/test_types.py` |

### 2. 数据转换（axond/data_converter.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 2.1 | `dataframe_to_events(df, symbol)` 将 OHLCV DataFrame 转换为 axon 事件列表，每个事件包含 type/timestamp_ns/symbol/open/high/low/close/volume | `tests/unit/axond/test_data_converter.py` |
| 2.2 | `dataframe_to_events` 正确处理空 DataFrame（返回空列表） | `tests/unit/axond/test_data_converter.py` |
| 2.3 | `dataframe_to_events` 正确处理非 UTC 时间戳（自动转 UTC） | `tests/unit/axond/test_data_converter.py` |
| 2.4 | `dataframe_to_events` 正确处理列名大小写不敏感（Open/open/Open） | `tests/unit/axond/test_data_converter.py` |
| 2.5 | `strategy_signals_to_events(signals, symbol)` 将信号列表转换为订单事件 | `tests/unit/axond/test_data_converter.py` |
| 2.6 | `strategy_signals_to_events` 处理 buy 信号生成 Buy 方向订单 | `tests/unit/axond/test_data_converter.py` |
| 2.7 | `strategy_signals_to_events` 处理 sell 信号生成 Sell 方向订单 | `tests/unit/axond/test_data_converter.py` |
| 2.8 | `strategy_signals_to_events` 为每个订单分配递增的 order_id | `tests/unit/axond/test_data_converter.py` |
| 2.9 | `axon_result_to_dict(result)` 将 axon RunResult 转换为 QuantCell 结果字典 | `tests/unit/axond/test_data_converter.py` |
| 2.10 | `events_to_dataframe(events)` 将 axon 事件列表转换回 DataFrame | `tests/unit/axond/test_data_converter.py` |

### 3. 包结构（axond/__init__.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 3.1 | `from axond import types` 可导入所有类型 | `tests/unit/axond/test_init.py` |
| 3.2 | `from axond import data_converter` 可导入所有转换函数 | `tests/unit/axond/test_init.py` |

## 实现步骤（TDD 循环）

### Cycle 1: 类型定义

```
RED:   写 test_types.py 中 1.1-1.4 的枚举测试 → 失败
GREEN: 创建 axond/__init__.py + axond/types.py，实现枚举 → 通过
RED:   写 test_types.py 中 1.5-1.6 的 InstrumentId 测试 → 失败
GREEN: 在 types.py 中实现 InstrumentId → 通过
RED:   写 test_types.py 中 1.7-1.11 的 dataclass 测试 → 失败
GREEN: 在 types.py 中实现 Bar, QuoteTick, TradeTick, Position, AccountBalance → 通过
```

### Cycle 2: 数据转换

```
RED:   写 test_data_converter.py 中 2.1-2.4 的 DataFrame 转换测试 → 失败
GREEN: 创建 axond/data_converter.py，实现 dataframe_to_events() → 通过
RED:   写 test_data_converter.py 中 2.5-2.8 的信号转换测试 → 失败
GREEN: 在 data_converter.py 中实现 strategy_signals_to_events() → 通过
RED:   写 test_data_converter.py 中 2.9-2.10 的反向转换测试 → 失败
GREEN: 在 data_converter.py 中实现 axon_result_to_dict() + events_to_dataframe() → 通过
```

### Cycle 3: 包导出

```
RED:   写 test_init.py 的导入测试 → 失败
GREEN: 在 axond/__init__.py 中添加导出 → 通过
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `backend/axond/__init__.py` | 新建：axon 集成层包 |
| `backend/axond/types.py` | 新建：统一类型定义 |
| `backend/axond/data_converter.py` | 新建：DataFrame ↔ axon 事件转换 |
| `backend/tests/unit/axond/__init__.py` | 新建：测试包 |
| `backend/tests/unit/axond/test_types.py` | 新建：类型测试 |
| `backend/tests/unit/axond/test_data_converter.py` | 新建：转换器测试 |
| `backend/tests/unit/axond/test_init.py` | 新建：包导入测试 |

## 验证

```bash
cd backend
python -m pytest tests/unit/axond/ -v
```

所有测试通过后，P1 完成。
