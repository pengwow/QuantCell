# 回测模块 (Backtest Module)

## 概述

回测模块提供量化交易策略的回测执行和分析功能。支持单货币对和多货币对回测，提供完整的回测结果分析和回放功能。

## 功能特性

- **策略回测**: 支持多种策略的回测执行
- **多货币对回测**: 支持多货币对并行回测
- **回测分析**: 提供详细的回测结果分析
- **数据完整性检查**: 检查回测数据的完整性
- **回放功能**: 支持回测结果的可视化回放
- **结果管理**: 回测结果的保存、加载和删除

## 目录结构

```
backtest/
├── __init__.py          # 模块导出
├── routes.py            # API路由定义
├── schemas.py           # 数据模型定义
├── service.py           # 回测服务实现
├── data_integrity.py    # 数据完整性检查
├── data_downloader.py   # 数据下载器
├── data_manager.py      # 数据管理器
└── README.md            # 模块文档
```

## API端点

### 回测管理

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/backtest/list` | 获取回测列表 |
| POST | `/api/backtest/run` | 执行回测 |
| POST | `/api/backtest/stop` | 终止回测 |
| GET | `/api/backtest/{backtest_id}` | 获取回测详情 |
| DELETE | `/api/backtest/delete/{backtest_id}` | 删除回测结果 |

### 回测分析

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/backtest/analyze` | 分析回测结果 |
| GET | `/api/backtest/{backtest_id}/symbols` | 获取回测货币对列表 |
| GET | `/api/backtest/{backtest_id}/replay` | 获取回测回放数据 |

### 数据管理

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/backtest/check-data` | 检查数据完整性 |
| POST | `/api/backtest/download-data` | 下载缺失数据 |

## 使用示例

### 执行回测

```python
from backtest import BacktestService

service = BacktestService()

# 配置策略
strategy_config = {
    "strategy_name": "SmaCross",
    "params": {"n1": 10, "n2": 20}
}

# 配置回测
backtest_config = {
    "symbols": ["BTCUSDT"],
    "interval": "1d",
    "start_time": "2023-01-01 00:00:00",
    "end_time": "2023-12-31 23:59:59",
    "initial_cash": 10000.0,
    "commission": 0.001
}

# 执行回测
result = service.run_backtest(strategy_config, backtest_config)
print(result)
```

### 获取回测结果

```python
# 获取回测列表
backtests = service.list_backtest_results()

# 分析回测结果
analysis = service.analyze_backtest("backtest_id")

# 获取回放数据
replay_data = service.get_replay_data("backtest_id", symbol="BTCUSDT")
```

## 数据模型

### BacktestConfig

回测配置模型：

```python
class BacktestConfig(BaseModel):
    symbols: List[str]          # 回测交易对列表
    interval: str               # K线周期
    start_time: str             # 开始时间
    end_time: str               # 结束时间
    initial_cash: float         # 初始资金
    commission: float           # 手续费率
    exclusive_orders: bool      # 是否取消未完成订单
```

### StrategyConfig

策略配置模型：

```python
class StrategyConfig(BaseModel):
    strategy_name: str          # 策略名称
    params: Dict[str, Any]      # 策略参数
```

### BacktestResult

回测结果模型：

```python
class BacktestResult(BaseModel):
    task_id: str                # 任务ID
    strategy_name: str          # 策略名称
    backtest_config: BacktestConfig  # 回测配置
    metrics: Dict[str, Any]     # 回测指标
    trades: List[Dict]          # 交易记录
    equity_curve: List[Dict]    # 资金曲线
    strategy_data: List[Dict]   # 策略数据
```

## 依赖

- FastAPI: Web框架
- Pydantic: 数据验证
- Pandas: 数据处理
- Loguru: 日志记录

## 注意事项

1. 回测执行需要完整的历史数据
2. 多货币对回测会并行执行
3. 回测结果会保存到文件系统和数据库
4. 数据完整性检查会在回测前自动执行
