# 回测引擎验证模块

## 概述

本模块用于系统性验证 QuantCell 回测引擎计算结果的准确性和可靠性。提供多层次的验证指标体系和完整的验证报告功能。

## 核心功能

### 1. 验证指标体系

#### 收益率验证
- `TotalReturnValidator` - 总收益率验证
- `AnnualizedReturnValidator` - 年化收益率验证
- `DailyReturnsValidator` - 日收益率序列验证
- `CumulativeReturnsValidator` - 累计收益率曲线验证

#### 交易信号验证
- `SignalCountValidator` - 信号数量验证
- `SignalTimingValidator` - 信号时间验证
- `SignalTypeValidator` - 信号类型验证
- `SignalPriceValidator` - 信号价格验证

#### 持仓变化验证
- `PositionQuantityValidator` - 持仓数量验证
- `PositionValueValidator` - 持仓价值验证
- `PositionChangeTimingValidator` - 持仓变化时间验证

#### 资金曲线验证
- `EquityCurveValidator` - 资金曲线验证
- `DrawdownValidator` - 回撤验证
- `CashBalanceValidator` - 现金余额验证

#### 交易记录验证
- `TradeCountValidator` - 交易数量验证
- `TradePnLValidator` - 交易盈亏验证
- `TradeFeeValidator` - 交易费用验证
- `TradeTimingValidator` - 交易时间验证

#### 绩效指标验证
- `SharpeRatioValidator` - 夏普比率验证
- `MaxDrawdownValidator` - 最大回撤验证
- `WinRateValidator` - 胜率验证
- `ProfitFactorValidator` - 盈利因子验证

### 2. 引擎特定验证

#### 事件引擎验证
- `EventEngineValidator` - 事件引擎整体验证
- `EventProcessingValidator` - 事件处理验证
- `OrderExecutionValidator` - 订单执行验证
- `StateConsistencyValidator` - 状态一致性验证

#### 向量引擎验证
- `VectorEngineValidator` - 向量引擎整体验证
- `VectorizedCalculationValidator` - 向量化计算验证
- `SignalProcessingValidator` - 信号处理验证
- `NumbaConsistencyValidator` - Numba一致性验证

## 快速开始

### 基本使用

```python
from strategy.validation import quick_validate

# 准备期望结果和实际结果
expected = {
    "total_return": 15.5,
    "max_drawdown": -5.2,
    "trade_count": 10,
    "sharpe_ratio": 1.2,
    "equity_curve": [10000, 10100, 10200, ...],
}

actual = {
    "total_return": 15.3,
    "max_drawdown": -5.1,
    "trade_count": 10,
    "sharpe_ratio": 1.18,
    "equity_curve": [10000, 10099, 10198, ...],
}

# 执行验证
suite = quick_validate(expected, actual, output_dir="./reports")

# 检查验证结果
if suite.all_passed():
    print("✅ 验证通过")
else:
    print("❌ 验证失败")
    print(f"通过率: {suite.get_summary()['pass_rate']*100:.2f}%")
```

### 使用验证套件

```python
from strategy.validation import BacktestValidator

validator = BacktestValidator()

# 验证收益率
results = validator.validate_returns(expected, actual)

# 验证交易信号
results = validator.validate_signals(expected, actual)

# 验证持仓变化
results = validator.validate_positions(expected, actual)

# 验证资金曲线
results = validator.validate_equity(expected, actual)

# 验证交易记录
results = validator.validate_trades(expected, actual)

# 验证绩效指标
results = validator.validate_metrics(expected, actual)

# 执行完整验证
suite = validator.validate_full(expected, actual, output_dir="./reports")
```

### 自定义验证套件

```python
from strategy.validation.core import ValidationSuite
from strategy.validation.validators import (
    TotalReturnValidator,
    SharpeRatioValidator,
    MaxDrawdownValidator,
)

# 创建验证套件
suite = ValidationSuite(
    name="CustomValidation",
    description="自定义验证套件"
)

# 添加验证器
suite.add_validator(TotalReturnValidator(threshold=0.02))
suite.add_validator(SharpeRatioValidator(threshold=0.1))
suite.add_validator(MaxDrawdownValidator(threshold=0.02))

# 执行验证
results = suite.run(expected, actual)

# 获取摘要
summary = suite.get_summary()
print(f"通过率: {summary['pass_rate']*100:.2f}%")
```

### 使用验证案例

```python
from strategy.validation.cases import SmaCrossValidationCase

# 创建验证案例
case = SmaCrossValidationCase(n1=5, n2=10)

# 执行验证
result = case.run_validation()

print(f"案例: {result['case_name']}")
print(f"通过: {result['passed']}")
print(f"总验证项: {result['summary']['total']}")
```

## 命令行工具

### 运行所有验证案例

```bash
cd backend
python -m strategy.validation.cli --all
```

### 运行特定案例

```bash
python -m strategy.validation.cli --case sma_cross
```

### 保存报告

```bash
python -m strategy.validation.cli --all --output ./reports
```

### 详细输出

```bash
python -m strategy.validation.cli --all --verbose
```

## 验证阈值配置

### 默认阈值

```python
from strategy.validation.core import ValidationThresholds

thresholds = ValidationThresholds(
    returns_tolerance=0.01,          # 收益率容差 1%
    signal_timing_tolerance=1,       # 信号时间容差 1个周期
    position_tolerance=0.001,        # 持仓容差 0.1%
    equity_tolerance=0.01,           # 资金容差 1%
    trade_count_tolerance=0,         # 交易数量容差 0笔
    metrics_tolerance=0.05,          # 指标容差 5%
)
```

### 自定义阈值

```python
from strategy.validation.validators import TotalReturnValidator

# 创建自定义阈值的验证器
validator = TotalReturnValidator(threshold=0.02)  # 2% 容差

# 严格模式
validator = TotalReturnValidator(strict=True)  # 任何偏差都视为错误
```

## 报告格式

### Markdown 报告

```python
from strategy.validation.reports import ReportGenerator

generator = ReportGenerator()
report = generator.generate(results, summary, format_type="markdown")
```

### JSON 报告

```python
report = generator.generate(results, summary, format_type="json")
```

### HTML 报告

```python
report = generator.generate(results, summary, format_type="html")
```

### 保存多种格式

```python
saved_files = generator.save_from_suite(
    suite,
    output_dir="./reports",
    formats=["markdown", "json", "html"]
)
```

## 扩展验证器

### 创建自定义验证器

```python
from strategy.validation.core import BaseValidator, ValidationResult, ValidationSeverity
from strategy.validation.core.registry import register_validator

@register_validator("custom_validator")
class CustomValidator(BaseValidator):
    name = "CustomValidator"
    description = "自定义验证器示例"
    default_threshold = 0.01

    def validate(self, expected, actual, **kwargs):
        # 实现验证逻辑
        difference = abs(expected - actual)
        passed = difference <= self.threshold

        return self.create_result(
            passed=passed,
            message="自定义验证通过" if passed else "自定义验证失败",
            expected=expected,
            actual=actual,
            difference=difference,
        )
```

## 验证案例开发

### 创建验证案例

```python
from strategy.validation.cases import ValidationCase, generate_sample_data

class MyStrategyValidationCase(ValidationCase):
    name = "MyStrategyCase"
    description = "我的策略验证案例"

    def setup(self):
        self.data = generate_sample_data(
            start_date="2023-01-01",
            periods=100,
            trend="up",
        )

    def generate_expected_results(self):
        # 手动计算期望结果
        return {
            "total_return": 10.0,
            "trade_count": 5,
        }

    def generate_actual_results(self):
        # 调用回测引擎获取实际结果
        return self.run_backtest()

    def get_validation_config(self):
        return {
            "thresholds": {
                "returns_tolerance": 0.01,
            }
        }
```

## 异常处理

### 验证异常

```python
from strategy.validation.core.exceptions import (
    ValidationError,
    ThresholdExceededError,
)

try:
    result = validator.validate(expected, actual)
except ThresholdExceededError as e:
    print(f"阈值超出: {e}")
    print(f"期望值: {e.expected_value}")
    print(f"实际值: {e.actual_value}")
    print(f"差异: {e.difference}")
    print(f"阈值: {e.threshold}")
```

## 最佳实践

1. **选择合适的阈值**：根据策略特性和数据精度选择合适的验证阈值
2. **分层验证**：先验证基础指标（收益率、交易数量），再验证复杂指标（夏普比率）
3. **定期验证**：在修改回测引擎后运行完整验证套件
4. **保存历史报告**：保留验证报告以便追踪问题
5. **自定义案例**：为关键策略创建专门的验证案例

## 目录结构

```
backend/strategy/validation/
├── __init__.py                    # 模块入口
├── core/                          # 核心组件
│   ├── base.py                    # 验证器基类
│   ├── registry.py                # 验证器注册表
│   └── exceptions.py              # 异常定义
├── validators/                    # 验证器实现
│   ├── returns_validator.py       # 收益率验证
│   ├── signals_validator.py       # 信号验证
│   ├── positions_validator.py     # 持仓验证
│   ├── equity_validator.py        # 资金验证
│   ├── trades_validator.py        # 交易验证
│   └── metrics_validator.py       # 指标验证
├── engines/                       # 引擎验证
│   ├── event_engine_validator.py  # 事件引擎
│   └── vector_engine_validator.py # 向量引擎
├── cases/                         # 验证案例
│   ├── base_case.py               # 案例基类
│   ├── sma_cross_case.py          # SMA交叉案例
│   └── buy_hold_case.py           # 买入持有案例
├── reports/                       # 报告生成
│   ├── report_generator.py        # 报告生成器
│   └── formatters.py              # 格式化工具
├── runner.py                      # 验证运行器
└── cli.py                         # 命令行接口
```

## 依赖

- numpy >= 1.20.0
- pandas >= 1.3.0
- loguru >= 0.6.0

## 许可证

MIT License
