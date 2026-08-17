# P5: AI 策略生成迁移

## 目标

更新 AI 策略生成模板和代码验证器，使用 axon 策略 API 替代 nautilus API。

## 依赖

- P3 完成（策略框架）

## TDD 行为清单

### 1. 策略生成模板（ai_model/prompts/templates/strategy_generation.txt）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 1.1 | 模板生成的策略代码 `from backtest.strategies.base import AxonStrategy` | `tests/unit/ai_model/test_strategy_generation.py` |
| 1.2 | 模板生成的策略代码 `from axond.types import Bar, OrderType` | `tests/unit/ai_model/test_strategy_generation.py` |
| 1.3 | 模板生成的策略代码继承 `AxonStrategy` 而非 nautilus Strategy | `tests/unit/ai_model/test_strategy_generation.py` |
| 1.4 | 模板生成的策略代码使用 `self.buy()`/`self.sell()` 下单 | `tests/unit/ai_model/test_strategy_generation.py` |
| 1.5 | 模板生成的策略代码使用 `self.get_position_size()` 查询持仓 | `tests/unit/ai_model/test_strategy_generation.py` |
| 1.6 | 模板生成的策略代码不包含任何 `nautilus_trader` 导入 | `tests/unit/ai_model/test_strategy_generation.py` |

### 2. 代码验证器（ai_model/code_validator.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 2.1 | 验证器识别 `from backtest.strategies.base import AxonStrategy` 为有效导入 | `tests/unit/ai_model/test_code_validator_axon.py` |
| 2.2 | 验证器识别 `from axond.types import Bar` 为有效导入 | `tests/unit/ai_model/test_code_validator_axon.py` |
| 2.3 | 验证器拒绝 `from nautilus_trader.trading.strategy import Strategy` | `tests/unit/ai_model/test_code_validator_axon.py` |
| 2.4 | 验证器接受继承 AxonStrategy 的策略类 | `tests/unit/ai_model/test_code_validator_axon.py` |
| 2.5 | 验证器拒绝继承 nautilus Strategy 的策略类 | `tests/unit/ai_model/test_code_validator_axon.py` |

### 3. AST 策略检测（utils/strategy_ast_parser.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 3.1 | `is_axon_strategy(code)` 检测继承 AxonStrategy 的策略返回 True | `tests/unit/utils/test_axon_ast_parser.py` |
| 3.2 | `is_axon_strategy(code)` 检测继承 StrategyBase 的策略返回 True | `tests/unit/utils/test_axon_ast_parser.py` |
| 3.3 | `is_axon_strategy(code)` 检测继承 nautilus Strategy 的策略返回 False | `tests/unit/utils/test_axon_ast_parser.py` |
| 3.4 | `is_axon_strategy(code)` 检测无继承关系的代码返回 False | `tests/unit/utils/test_axon_ast_parser.py` |

### 4. 策略服务类型检测（strategy/service.py）

| # | 行为描述 | 测试文件 |
|---|---------|---------|
| 4.1 | `_detect_strategy_type()` 检测 AxonStrategy 策略返回 "axon" | `tests/unit/strategy/test_service_detect.py` |
| 4.2 | `_detect_strategy_type()` 检测 StrategyBase 策略返回 "core" | `tests/unit/strategy/test_service_detect.py` |
| 4.3 | `_detect_strategy_type()` 检测 nautilus 策略返回 "unknown" | `tests/unit/strategy/test_service_detect.py` |

## 实现步骤

### Cycle 1: 策略生成模板

```
RED:   写 test_strategy_generation.py 1.1-1.6 → 失败
GREEN: 重写 ai_model/prompts/templates/strategy_generation.txt → 通过
```

### Cycle 2: 代码验证器

```
RED:   写 test_code_validator_axon.py 2.1-2.5 → 失败
GREEN: 更新 ai_model/code_validator.py → 通过
```

### Cycle 3: AST 检测

```
RED:   写 test_axon_ast_parser.py 3.1-3.4 → 失败
GREEN: 更新 utils/strategy_ast_parser.py → 通过
```

### Cycle 4: 策略服务检测

```
RED:   写 test_service_detect.py 4.1-4.3 → 失败
GREEN: 更新 strategy/service.py 中 _detect_strategy_type() → 通过
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `backend/ai_model/prompts/templates/strategy_generation.txt` | 重写：axon 策略模板 |
| `backend/ai_model/code_validator.py` | 更新：axon 验证 |
| `backend/utils/strategy_ast_parser.py` | 更新：axon 检测 |
| `backend/strategy/service.py` | 更新：删除 nautilus 检测 |
| `backend/tests/unit/ai_model/test_strategy_generation.py` | 新建：模板测试 |
| `backend/tests/unit/ai_model/test_code_validator_axon.py` | 新建：验证器测试 |
| `backend/tests/unit/utils/test_axon_ast_parser.py` | 新建：AST 测试 |
| `backend/tests/unit/strategy/test_service_detect.py` | 新建：检测测试 |

## 验证

```bash
cd backend
python -m pytest tests/unit/ai_model/ tests/unit/utils/test_axon_ast_parser.py tests/unit/strategy/test_service_detect.py -v
```
