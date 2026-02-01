# QUANTCELL 回测命令行工具使用指南

## 概述

`scripts/backtest_cli.py` 是 QUANTCELL 的命令行回测工具，支持通过命令行方式调用回测引擎进行回测。

## 安装依赖

```bash
pip install numpy pandas numba loguru
```

## 基本用法

### 1. 使用默认参数运行策略

```bash
cd backend
python scripts/backtest_cli.py --strategy grid_trading_v2
```

这将使用默认参数运行网格交易策略，并生成测试数据。

### 2. 指定策略参数

```bash
cd backend
python scripts/backtest_cli.py --strategy grid_trading_v2 --params '{"grid_count": 20, "position_size": 0.01}'
```

### 3. 使用自定义数据文件

```bash
cd backend
python scripts/backtest_cli.py --strategy grid_trading_v2 --data /path/to/data.csv
```

数据文件必须是 CSV 格式，包含以下列：
- `Open`: 开盘价
- `High`: 最高价
- `Low`: 最低价
- `Close`: 收盘价
- `Volume`: 成交量

### 4. 指定输出格式和文件

```bash
cd backend
python scripts/backtest_cli.py --strategy grid_trading_v2 --output-format json --output results.json
```

### 5. 显示详细日志

```bash
cd backend
python scripts/backtest_cli.py --strategy grid_trading_v2 --verbose
```

## 命令行参数

### 必需参数

| 参数 | 简写 | 类型 | 说明 | 示例 |
|------|--------|------|------|--------|
| `--strategy` | `-s` | str | 策略文件名（不带.py后缀） | `grid_trading_v2` |

### 可选参数

| 参数 | 简写 | 类型 | 默认值 | 说明 | 示例 |
|------|--------|------|----------|------|--------|
| `--params` | `-p` | str | `{}` | 策略参数（JSON格式） | `'{"grid_count": 20, "position_size": 0.01}'` |
| `--data` | `-d` | str | `None` | 数据文件路径（CSV格式） | `/path/to/data.csv` |
| `--init-cash` | | float | `100000.0` | 初始资金 | `50000.0` |
| `--fees` | | float | `0.001` | 手续费率 | `0.0005` |
| `--slippage` | | float | `0.0001` | 滑点 | `0.00005` |
| `--output-format` | `-f` | str | `json` | 输出格式（json 或 csv） | `csv` |
| `--output` | `-o` | str | `None` | 输出文件路径 | `results.json` |
| `--verbose` | `-v` | flag | `False` | 显示详细日志 | |

## 使用示例

### 示例 1: 基本回测

```bash
cd backend
python scripts/backtest_cli.py --strategy grid_trading_v2
```

输出：
```
======================================================================
开始回测
======================================================================

成功加载策略: GridTradingStrategy
生成测试数据
数据范围: 1000 条K线
价格范围: [49323.65, 50781.78]

运行回测...
回测完成

======================================================================
回测结果
======================================================================

交易对: BTCUSDT
  最终现金: 99974.29
  最终持仓: 0.0000
  交易数量: 96

  绩效指标:
    total_pnl: -0.8629
    total_fees: 47.0369
    win_rate: 0.5000
    sharpe_ratio: 0.0000
    trade_count: 96
    final_equity: 99974.2861

结果已保存到: backtest_results_20240201_162545.json
```

### 示例 2: 自定义参数回测

```bash
cd backend
python scripts/backtest_cli.py \
  --strategy grid_trading_v2 \
  --params '{"grid_count": 20, "auto_range_pct": 0.15, "position_size": 0.005}' \
  --init-cash 50000.0 \
  --fees 0.0005 \
  --verbose
```

### 示例 3: 使用真实数据回测

```bash
cd backend
python scripts/backtest_cli.py \
  --strategy grid_trading_v2 \
  --data /path/to/btc_data.csv \
  --output-format csv \
  --output backtest_results.csv
```

### 示例 4: 批量回测（Shell 脚本）

```bash
#!/bin/bash

# 定义策略参数数组
declare -a PARAMS=(
  '{"grid_count": 10, "position_size": 0.01}'
  '{"grid_count": 20, "position_size": 0.005}'
  '{"grid_count": 30, "position_size": 0.003}'
)

# 运行多次回测
for i in "${!PARAMS[@]}"; do
  echo "运行回测配置: $i"
  cd backend
  python scripts/backtest_cli.py \
    --strategy grid_trading_v2 \
    --params "$i" \
    --output "results_$(date +%s).json"
done
```

### 示例 5: Python 脚本批量回测

```python
import subprocess
import json

# 定义多个策略配置
configs = [
    {
        'strategy': 'grid_trading_v2',
        'params': {'grid_count': 10, 'position_size': 0.01},
        'init_cash': 100000.0
    },
    {
        'strategy': 'grid_trading_v2',
        'params': {'grid_count': 20, 'position_size': 0.005},
        'init_cash': 100000.0
    },
    {
        'strategy': 'grid_trading_v2',
        'params': {'grid_count': 30, 'position_size': 0.003},
        'init_cash': 100000.0
    }
]

# 运行每次配置
for i, config in enumerate(configs):
    print(f"运行配置 {i+1}/{len(configs)}")
    
    # 构建命令
    cmd = [
        'python', 'scripts/backtest_cli.py',
        '--strategy', config['strategy'],
        '--params', json.dumps(config['params']),
        '--init-cash', str(config['init_cash']),
        '--output', f"results_{i+1}.json"
    ]
    
    # 运行命令
    subprocess.run(cmd, check=True)
    print(f"配置 {i+1} 完成\n")
```

## 输出格式

### JSON 格式

```json
{
  "BTCUSDT": {
    "symbol": "BTCUSDT",
    "cash": 99974.2861,
    "final_position": 0.0,
    "trade_count": 96,
    "metrics": {
      "total_pnl": -0.8629,
      "total_fees": 47.0369,
      "win_rate": 0.5,
      "sharpe_ratio": 0.0,
      "trade_count": 96,
      "final_equity": 99974.2861
    }
  }
}
```

### CSV 格式

```csv
Symbol,Cash,FinalPosition,TradeCount,TotalPnl,TotalFees,WinRate,SharpeRatio,FinalEquity
BTCUSDT,99974.29,0.0000,96,-0.86,47.04,0.5000,0.0000,99974.29
```

## 数据文件格式

如果使用 `--data` 参数指定数据文件，文件必须是 CSV 格式，包含以下列：

| 列名 | 类型 | 说明 | 示例 |
|--------|------|------|--------|
| `Open` | float | 开盘价 | `50000.0` |
| `High` | float | 最高价 | `50100.0` |
| `Low` | float | 最低价 | `49900.0` |
| `Close` | float | 收盘价 | `50000.0` |
| `Volume` | float | 成交量 | `1000.0` |

示例数据文件：

```csv
Date,Open,High,Low,Close,Volume
2024-01-01 00:00:00,50000.0,50100.0,49900.0,50000.0,1000.0
2024-01-01 01:00:00,50000.0,50100.0,49900.0,50000.0,1000.0
2024-01-01 02:00:00,50000.0,50100.0,49900.0,50000.0,1000.0
```

## 策略参数说明

### GridTradingStrategy 参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|----------|------|
| `grid_count` | int | `10` | 网格数量 |
| `price_range` | list | `None` | 价格区间 `[下限, 上限]`，None 则自动计算 |
| `auto_range_pct` | float | `0.1` | 自动计算价格区间的百分比（10%） |
| `position_size` | float | `1.0` | 每个网格的仓位大小 |
| `initial_capital` | float | `10000` | 初始资金 |
| `enable_stop_loss` | bool | `False` | 是否启用止损 |
| `stop_loss_pct` | float | `0.2` | 止损百分比（20%） |
| `enable_take_profit` | bool | `False` | 是否启用止盈 |
| `take_profit_pct` | float | `0.3` | 止盈百分比（30%） |

## 常见问题

### Q1: 策略加载失败

**问题**: `ModuleNotFoundError: No module named 'grid_trading_v2'`

**解决**: 
1. 确保策略文件在 `strategies/` 目录下
2. 确保策略文件名正确（不带.py后缀）
3. 检查策略文件中是否定义了对应的类

### Q2: 数据文件格式错误

**问题**: `数据文件缺少必要列: Open`

**解决**: 
1. 确保数据文件包含所有必需列：`Open`, `High`, `Low`, `Close`, `Volume`
2. 确保数据文件的第一列是日期索引
3. 使用 `pd.read_csv(data_path, index_col=0, parse_dates=True)` 加载数据

### Q3: JSON 参数解析失败

**问题**: `策略参数解析失败: {"grid_count": 20}`

**解决**: 
1. 确保参数是有效的 JSON 格式
2. 在 Shell 中使用单引号包裹 JSON 字符串
3. 使用在线 JSON 验证工具验证 JSON 格式

## 性能优化

### 1. 使用 Numba JIT

所有核心函数都使用 Numba JIT 编译，性能提升 50-100x。

### 2. 向量化回测

使用 `VectorEngine` 进行向量化回测，支持多资产并行回测。

### 3. 批量回测

使用脚本批量运行多个配置，充分利用多核 CPU。

## 下一步

1. **添加更多策略**: 在 `strategies/` 目录下添加更多策略
2. **优化性能**: 进一步优化 Numba 函数
3. **添加可视化**: 添加结果可视化功能
4. **添加参数优化**: 添加参数自动优化功能

## 总结

`scripts/backtest_cli.py` 提供了完整的命令行回测功能，支持：

- ✅ 策略动态加载
- ✅ 自定义参数配置
- ✅ 真实数据回测
- ✅ 测试数据生成
- ✅ 多种输出格式（JSON/CSV）
- ✅ 详细日志控制
- ✅ 批量回测支持

通过命令行工具，您可以轻松地进行策略回测、参数优化和批量测试！
