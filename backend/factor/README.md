# 因子计算模块 (Factor Module)

## 概述

因子计算模块提供量化交易因子计算和管理功能，支持多种类型的因子计算和分析。

## 功能特性

- **因子管理**：获取、添加、删除自定义因子
- **因子计算**：支持单因子、多因子、所有因子计算
- **因子分析**：IC分析、IR分析、分组分析、单调性检验、稳定性检验
- **因子验证**：验证因子表达式有效性

## 支持的因子类型

### 价格相关因子
- `close`: 收盘价
- `open`: 开盘价
- `high`: 最高价
- `low`: 最低价
- `volume`: 成交量
- `vwap`: 成交量加权平均价
- `amount`: 成交额

### 动量因子
- `momentum_5d`: 5日动量
- `momentum_10d`: 10日动量
- `momentum_20d`: 20日动量
- `momentum_60d`: 60日动量

### 波动率因子
- `volatility_5d`: 5日波动率
- `volatility_10d`: 10日波动率
- `volatility_20d`: 20日波动率
- `volatility_60d`: 60日波动率

### 量价因子
- `turnover_rate`: 换手率
- `volume_change`: 成交量变化率
- `price_volume`: 价量因子

### 技术指标因子
- `ma_5d`: 5日均线
- `ma_10d`: 10日均线
- `ma_20d`: 20日均线
- `ma_60d`: 60日均线
- `macd`: MACD指标
- `rsi_14d`: 14日RSI
- `kdj`: KDJ指标
- `bollinger`: 布林带

### 财务因子
- `pe`: 市盈率
- `pb`: 市净率
- `roe`: 净资产收益率
- `roa`: 总资产收益率
- `profit_growth`: 利润增长率

## 目录结构

```
factor/
├── __init__.py          # 模块导出
├── README.md           # 模块文档
├── routes.py           # API路由
├── schemas.py          # Pydantic模型
├── service.py          # 业务服务
└── tests/              # 测试目录
    ├── __init__.py
    ├── test_routes.py
    └── test_service.py
```

## API端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/factor/list` | 获取因子列表 |
| GET | `/api/factor/expression/{name}` | 获取因子表达式 |
| POST | `/api/factor/add` | 添加自定义因子 |
| DELETE | `/api/factor/delete/{name}` | 删除自定义因子 |
| POST | `/api/factor/calculate` | 计算单因子 |
| POST | `/api/factor/calculate-multi` | 计算多因子 |
| POST | `/api/factor/calculate-all` | 计算所有因子 |
| POST | `/api/factor/validate` | 验证因子表达式 |
| POST | `/api/factor/correlation` | 计算因子相关性 |
| POST | `/api/factor/stats` | 获取因子统计 |
| POST | `/api/factor/ic` | 计算IC |
| POST | `/api/factor/ir` | 计算IR |
| POST | `/api/factor/group-analysis` | 分组分析 |
| POST | `/api/factor/monotonicity` | 单调性检验 |
| POST | `/api/factor/stability` | 稳定性检验 |

## 使用示例

### 获取因子列表

```python
from backend.factor import FactorService

service = FactorService()
factors = service.get_factor_list()
print(factors)
```

### 计算单因子

```python
from backend.factor import FactorService

service = FactorService()
result = service.calculate_factor(
    factor_name="momentum_5d",
    instruments=["BTCUSDT", "ETHUSDT"],
    start_time="2023-01-01",
    end_time="2023-12-31",
    freq="day"
)
print(result)
```

### 添加自定义因子

```python
from backend.factor import FactorService

service = FactorService()
service.add_factor(
    factor_name="my_factor",
    factor_expression="$close - $open"
)
```

## 依赖

- QLib: 量化投资库
- pandas: 数据处理
- numpy: 数值计算
- scipy: 科学计算

## 作者

QuantCell Team

## 版本

1.0.0
