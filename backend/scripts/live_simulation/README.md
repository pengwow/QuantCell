# QuantCell 实盘交易模拟测试系统

一套全面的测试代码系统，用于模拟QuantCell框架的实盘交易环境。

## 功能特性

### 核心功能
- **数据加载模块**: 支持从CSV/Parquet文件或数据库加载历史交易数据
- **数据推送引擎**: 精确控制数据推送速度（1x, 2x, 5x, 10x, 自定义）
- **QuantCell连接**: WebSocket连接，支持身份验证和自动重连
- **Worker管理**: 动态加载策略，管理Worker生命周期
- **实时监控**: 监控开单情况、持仓状态、盈亏数据、交易信号
- **异常模拟**: 模拟网络延迟、数据中断、策略错误等异常情况
- **报告生成**: 生成HTML/JSON格式的测试报告

### 技术要求
- 支持可配置的参数化测试
- 完整的日志记录功能
- 支持至少8小时的连续模拟测试
- 模块化设计，易于扩展

## 安装

```bash
# 安装依赖
pip install typer websockets pandas pydantic loguru tomli tomli-w pytest pytest-asyncio
```

## 快速开始

### 1. 创建配置文件

```bash
python -m scripts.live_simulation.main create-config config.toml
```

### 2. 准备历史数据

将CSV格式的K线数据放入指定目录：

```
data/
  BTCUSDT_1m.csv
  ETHUSDT_1m.csv
```

CSV格式示例：
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,100.0,101.0,99.0,100.5,1000
2024-01-01 00:01:00,100.5,102.0,100.0,101.5,1500
```

### 3. 运行模拟测试

```bash
# 使用配置文件运行
python -m scripts.live_simulation.main run --config config.toml

# 或使用命令行参数
python -m scripts.live_simulation.main run \
  --data-path ./data \
  --strategy scripts/live_simulation/strategies/test_strategy.py \
  --speed 10.0 \
  --duration 8
```

### 4. 查看报告

测试完成后，报告将生成在 `./reports` 目录下：
- `simulation.json` - JSON格式详细数据
- `simulation.html` - HTML格式可视化报告

## 配置说明

配置文件支持 **TOML** 和 **JSON** 格式，推荐使用 TOML 格式。

### 数据配置 (data)
```toml
[data]
source_type = "file"  # 或 "database"
file_path = "./data"
symbols = ["BTCUSDT", "ETHUSDT"]
intervals = ["1m", "5m"]
```

### 推送配置 (push)
```toml
[push]
speed = 10.0  # 10倍速
realtime = false
batch_size = 1
batch_interval_ms = 1000
```

### Worker配置 (workers)
```toml
[[workers]]
strategy_path = "strategies/my_strategy.py"
strategy_class = "MyStrategy"
symbols = ["BTCUSDT"]

[workers.strategy_params]
param1 = "value1"
```

### 异常模拟配置 (exception_simulation)
```toml
[exception_simulation]
enabled = true
network_delay_ms = 100
network_delay_probability = 0.1
disconnect_interval_ms = 300000
```

## 命令行使用

### 运行测试
```bash
python -m scripts.live_simulation.main run [OPTIONS]

Options:
  --config, -c PATH       配置文件路径（支持.toml和.json）
  --data-path, -d PATH    数据文件路径
  --strategy, -s PATH     策略文件路径
  --speed FLOAT           数据推送速度倍率
  --duration FLOAT        测试持续时间（小时）
  --output, -o PATH       报告输出目录
```

### 创建默认配置
```bash
python -m scripts.live_simulation.main create-config config.toml
```

### 验证配置
```bash
python -m scripts.live_simulation.main validate config.toml
```

## 编写自定义策略

创建策略文件 `my_strategy.py`：

```python
from scripts.live_simulation.models import TradeSignal, SignalType

class MyStrategy:
    def __init__(self, params):
        self.params = params
        
    def initialize(self):
        print("Strategy initialized")
        
    def on_data(self, data):
        # 处理市场数据
        symbol = data["symbol"]
        close = data["close"]
        
        # 生成交易信号
        if some_condition:
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=data["timestamp"],
                price=close,
                volume=1.0,
                strategy_id="MyStrategy",
            )
        
        return None
```

## 测试

运行单元测试：

```bash
# 运行所有测试
pytest scripts/live_simulation/tests/

# 运行特定测试
pytest scripts/live_simulation/tests/test_models.py

# 运行集成测试
pytest scripts/live_simulation/tests/test_integration.py -v
```

## 项目结构

```
scripts/live_simulation/
├── __init__.py              # 包初始化
├── main.py                  # 主控制脚本
├── config.py                # 配置管理
├── models.py                # 数据模型
├── data_loader.py           # 数据加载模块
├── data_pusher.py           # 数据推送引擎
├── worker_manager.py        # Worker策略管理
├── monitor.py               # 监控脚本
├── exception_simulator.py   # 异常模拟器
├── report_generator.py      # 报告生成器
├── connection/              # 连接模块
│   ├── __init__.py
│   ├── quantcell_client.py  # QuantCell客户端
│   └── auth.py              # 认证模块
├── strategies/              # 策略示例
│   ├── __init__.py
│   └── test_strategy.py
├── tests/                   # 测试用例
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_data_loader.py
│   └── test_integration.py
└── example_config.toml      # 配置示例（TOML格式）
```

## 性能指标

系统会记录以下性能指标：

- **数据推送**: 推送速度、延迟、完成率
- **交易统计**: 信号数、订单数、成交率
- **盈亏情况**: 总盈亏、已实现/未实现盈亏、最大回撤、夏普比率
- **Worker状态**: 消息处理数、错误数、运行状态
- **异常记录**: 网络错误、数据错误、策略错误

## 注意事项

1. 确保QuantCell框架已启动并可连接
2. 历史数据格式需符合要求（包含timestamp, open, high, low, close, volume列）
3. 策略文件路径需正确，类名需匹配
4. 长时间测试建议启用日志记录
5. 异常模拟功能仅用于测试，生产环境请关闭
6. 配置文件推荐使用TOML格式，更加简洁易读

## 许可证

MIT License
