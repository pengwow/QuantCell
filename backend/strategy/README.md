# 策略模块 (Strategy Module)

## 概述

策略模块提供量化交易策略的管理、加载和执行功能。支持多种策略执行引擎，包括事件驱动引擎和向量化引擎。

## 功能特性

- **策略管理**: 策略的增删改查操作
- **策略加载**: 动态加载策略文件
- **策略解析**: 解析策略代码，提取参数信息
- **策略执行**: 支持回测和实盘两种模式
- **多种引擎**: 事件驱动引擎、向量化引擎等
- **策略验证**: 策略正确性验证

## 目录结构

```
strategy/
├── __init__.py              # 模块导出
├── routes.py                # API路由定义
├── schemas.py               # 数据模型定义
├── service.py               # 策略服务实现
├── strategy_base.py         # 策略基类
├── execution_engine.py      # 执行引擎
├── core/                    # 核心引擎模块
│   ├── __init__.py
│   ├── strategy_core.py     # 策略核心类
│   ├── strategy_base.py     # 策略基类
│   ├── event_engine.py      # 事件驱动引擎
│   ├── vector_engine.py     # 向量化引擎
│   └── ...
├── adapters/                # 适配器模块
│   ├── __init__.py
│   ├── vector_adapter.py
│   └── portfolio_adapter.py
├── trading_modules/         # 交易组件模块
│   ├── __init__.py
│   └── perpetual_contract.py
├── validation/              # 策略验证模块
│   ├── __init__.py
│   ├── core/
│   ├── validators/
│   └── ...
├── example/                 # 示例和测试
│   ├── strategies/
│   ├── tests/
│   └── ...
└── README.md                # 模块文档
```

## API端点

### 策略管理

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/strategy/list` | 获取策略列表 |
| POST | `/api/strategy/detail` | 获取策略详情 |
| POST | `/api/strategy/upload` | 上传策略文件 |
| POST | `/api/strategy/parse` | 解析策略脚本 |
| DELETE | `/api/strategy/{strategy_name}` | 删除策略 |

### 策略执行

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/strategy/{strategy_name}/execute` | 执行策略 |

## 使用示例

### 获取策略列表

```python
from strategy import StrategyService

service = StrategyService()
strategies = service.get_strategy_list()
for strategy in strategies:
    print(f"策略名称: {strategy['name']}")
```

### 上传策略文件

```python
# 上传策略文件
success = service.upload_strategy_file(
    strategy_name="my_strategy",
    file_content=strategy_code,
    version="1.0.0",
    description="我的策略"
)
```

### 加载策略

```python
# 加载策略类
strategy_class = service.load_strategy("sma_cross")
if strategy_class:
    # 创建策略实例
    strategy = strategy_class()
    # 设置参数
    strategy.n1 = 10
    strategy.n2 = 20
```

## 数据模型

### StrategyInfo

策略信息模型：

```python
class StrategyInfo(BaseModel):
    name: str                    # 策略名称
    file_name: str               # 策略文件名
    file_path: str               # 策略文件路径
    description: str             # 策略描述
    version: str                 # 策略版本
    params: List[StrategyParamInfo]  # 策略参数列表
    created_at: datetime         # 创建时间
    updated_at: datetime         # 更新时间
    code: Optional[str]          # 策略代码
    source: str                  # 策略来源
```

### StrategyParamInfo

策略参数信息模型：

```python
class StrategyParamInfo(BaseModel):
    name: str                    # 参数名称
    type: str                    # 参数类型
    default: Any                 # 默认值
    description: str             # 参数描述
    min: Optional[float]         # 最小值
    max: Optional[float]         # 最大值
    required: bool               # 是否必填
```

## 策略基类

### StrategyBase

所有策略的基类：

```python
from strategy import StrategyBase

class MyStrategy(StrategyBase):
    # 策略参数
    n1 = 10
    n2 = 20
    
    def init(self):
        """初始化策略"""
        pass
    
    def next(self):
        """策略逻辑"""
        if self.sma1 > self.sma2:
            self.buy()
        elif self.sma1 < self.sma2:
            self.sell()
```

## 执行引擎

### 事件驱动引擎

```python
from strategy.core import EventEngine

engine = EventEngine()
engine.add_strategy(MyStrategy)
engine.run()
```

### 向量化引擎

```python
from strategy.core import VectorEngine

engine = VectorEngine()
engine.add_strategy(MyStrategy)
engine.run()
```

## 依赖

- FastAPI: Web框架
- Pydantic: 数据验证
- Loguru: 日志记录

## 注意事项

1. 策略文件必须继承自StrategyBase
2. 策略参数必须定义为类属性
3. 策略文件名必须与策略类名匹配（小写+下划线）
4. 策略文件存储在backend/strategies目录下
