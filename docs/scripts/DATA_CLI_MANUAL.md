# Data CLI 数据管理命令行工具 - 帮助手册

## 目录
1. [概述](#概述)
2. [安装要求](#安装要求)
3. [命令语法](#命令语法)
4. [可用命令](#可用命令)
5. [参数说明](#参数说明)
6. [输入/输出格式](#输入输出格式)
7. [使用示例](#使用示例)
8. [错误代码与故障排除](#错误代码与故障排除)

---

## 概述

`data_cli.py` 是 QuantCell 量化交易平台的数据管理命令行工具，用于：
- 从交易所下载K线（蜡烛图）数据
- 管理下载任务
- 查询本地数据库中的数据
- 导出数据到CSV文件
- 从CSV文件导入数据

### 主要功能

| 功能模块 | 说明 |
|---------|------|
| **数据下载** | 支持多交易对、多时间周期批量下载 |
| **任务管理** | 创建、查询、监控下载任务 |
| **数据查询** | 查看本地存储的K线数据 |
| **数据导出** | 将数据库数据导出为CSV格式 |
| **数据导入** | 从CSV文件导入数据到数据库 |
| **数据删除** | 删除指定的本地数据 |

---

## 安装要求

### 系统要求
- **操作系统**: Linux/macOS/Windows
- **Python版本**: Python 3.8+
- **包管理工具**: uv (项目使用uv替代pip)

### 依赖项

该脚本依赖以下Python包（已包含在项目的 `uv.lock` 中）：

```
typer >= 0.9.0      # 命令行框架
loguru >= 0.7.0     # 日志记录
pandas >= 2.0.0     # 数据处理
sqlalchemy >= 2.0.0 # 数据库ORM
```

### 环境配置

1. **确保在项目根目录下运行**
2. **数据库必须已初始化** - 脚本会自动调用 `init_database_config()`
3. **系统配置** - 部分默认路径从 `SystemConfig` 读取

---

## 命令语法

### 基本语法

```bash
python data_cli.py [COMMAND] [OPTIONS]
```

### 获取帮助

```bash
# 查看所有命令
python data_cli.py --help

# 查看特定命令帮助
python data_cli.py download --help
python data_cli.py export csv --help
```

---

## 可用命令

### 1. download - 下载K线数据

从交易所下载K线数据并保存到本地。

```bash
python data_cli.py download [OPTIONS]
```

**必需参数：**

| 参数 | 短选项 | 类型 | 说明 |
|------|--------|------|------|
| `--symbols` | `-s` | List[str] | 交易对列表，可多次指定 |
| `--interval` | `-i` | List[str] | 时间周期列表，可多次指定 |
| `--start` | | str | 开始时间，格式：YYYYMMDD |
| `--end` | | str | 结束时间，格式：YYYYMMDD |

**可选参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--exchange` | `-e` | str | binance | 交易所名称 |
| `--candle-type` | | str | spot | 蜡烛图类型：spot/future |
| `--max-workers` | `-w` | int | 1 | 最大工作线程数 |
| `--mode` | `-m` | str | inc | 下载模式：inc(增量)/full(全量) |
| `--save-dir` | | str | None | 保存目录（默认从系统配置读取） |
| `--to-db/--no-db` | | bool | True | 是否直接写入数据库 |
| `--verbose` | `-v` | bool | False | 显示详细日志 |

**示例：**

```bash
# 下载BTCUSDT的日线数据
python data_cli.py download -s BTCUSDT -i 1d --start 20240101 --end 20241231

# 下载多个交易对、多个时间周期
python data_cli.py download -s BTCUSDT -s ETHUSDT -i 1h -i 4h --start 20240101 --end 20241231

# 下载合约数据
python data_cli.py download -s BTCUSDT -i 1h --start 20240101 --end 20241231 --candle-type future

# 全量下载模式
python data_cli.py download -s BTCUSDT -i 1d --start 20240101 --end 20241231 --mode full

# 启用详细日志
python data_cli.py download -s BTCUSDT -i 1d --start 20240101 --end 20241231 -v
```

---

### 2. status - 查询任务状态

查询下载任务的当前状态和进度。

```bash
python data_cli.py status [OPTIONS]
```

**参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--task-id` | `-t` | str | 必需 | 任务ID |
| `--watch` | `-w` | bool | False | 持续监控任务状态 |
| `--interval` | | int | 5 | 监控间隔（秒） |

**示例：**

```bash
# 单次查询任务状态
python data_cli.py status -t <task_id>

# 持续监控任务（每5秒刷新）
python data_cli.py status -t <task_id> --watch

# 自定义监控间隔
python data_cli.py status -t <task_id> --watch --interval 10
```

---

### 3. list-symbols - 列出支持的货币对

显示指定交易所支持的货币对列表。

```bash
python data_cli.py list-symbols [OPTIONS]
```

**参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--exchange` | `-e` | str | binance | 交易所名称 |
| `--limit` | `-l` | int | 50 | 显示数量限制 |

**示例：**

```bash
# 列出Binance支持的货币对
python data_cli.py list-symbols

# 限制显示数量
python data_cli.py list-symbols --limit 20
```

---

### 4. list-tasks - 列出下载任务

显示最近的K线数据下载任务列表。

```bash
python data_cli.py list-tasks [OPTIONS]
```

**参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--status` | `-s` | str | None | 状态过滤：pending/running/completed/failed |
| `--limit` | `-l` | int | 10 | 显示数量 |

**示例：**

```bash
# 列出所有任务
python data_cli.py list-tasks

# 只显示运行中的任务
python data_cli.py list-tasks --status running

# 显示更多任务
python data_cli.py list-tasks --limit 50
```

---

### 5. list-local-data - 查看本地K线数据

显示已下载到本地的K线数据信息。

```bash
python data_cli.py list-local-data [OPTIONS]
```

**参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--symbol` | `-s` | str | None | 指定交易对（如BTCUSDT） |
| `--data-source` | `-d` | str | None | 数据源（如binance, okx） |
| `--candle-type` | | str | spot | 蜡烛图类型：spot/future |
| `--limit` | `-l` | int | 50 | 显示交易对数量限制 |
| `--list-sources` | | bool | False | 列出所有可用的数据源 |

**示例：**

```bash
# 列出所有本地数据
python data_cli.py list-local-data

# 列出所有数据源
python data_cli.py list-local-data --list-sources

# 查看特定交易对的数据
python data_cli.py list-local-data -s BTCUSDT

# 查看特定数据源的数据
python data_cli.py list-local-data --data-source binance

# 查看合约数据
python data_cli.py list-local-data --candle-type future
```

---

### 6. delete-local-data - 删除本地K线数据

删除指定交易对的本地K线数据。

```bash
python data_cli.py delete-local-data [OPTIONS]
```

**参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--symbol` | `-s` | str | 必需 | 交易对 |
| `--interval` | `-i` | str | None | 时间周期（可选，不指定则删除所有周期） |
| `--exchange` | `-e` | str | binance | 交易所 |
| `--candle-type` | | str | spot | 蜡烛图类型：spot/future |
| `--yes` | `-y` | bool | False | 确认删除，不提示 |

**示例：**

```bash
# 删除BTCUSDT的所有数据（会提示确认）
python data_cli.py delete-local-data -s BTCUSDT

# 删除特定时间周期的数据
python data_cli.py delete-local-data -s BTCUSDT -i 1h

# 强制删除，不提示
python data_cli.py delete-local-data -s BTCUSDT -y

# 删除合约数据
python data_cli.py delete-local-data -s BTCUSDT --candle-type future -y
```

---

### 7. export - 导出数据

将数据库中的K线数据导出到文件。

#### 7.1 export csv - 导出为CSV

```bash
python data_cli.py export csv [OPTIONS]
```

**参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--symbol` | `-s` | str | 必需 | 交易对，如BTCUSDT |
| `--interval` | `-i` | str | 必需 | 时间周期，如1m, 5m, 1h, 1d |
| `--output` | `-o` | str | 必需 | 输出文件路径 |
| `--data-source` | `-d` | str | None | 数据源（如binance, okx） |
| `--candle-type` | | str | spot | 蜡烛图类型：spot/future |
| `--start` | | str | None | 开始时间（格式：YYYYMMDD） |
| `--end` | | str | None | 结束时间（格式：YYYYMMDD） |

**示例：**

```bash
# 导出BTCUSDT的1小时数据
python data_cli.py export csv -s BTCUSDT -i 1h -o btc_1h.csv

# 导出指定时间范围的数据
python data_cli.py export csv -s BTCUSDT -i 1d --start 20240101 --end 20241231 -o btc_2024.csv

# 导出特定数据源的数据
python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv --data-source binance

# 导出合约数据
python data_cli.py export csv -s BTCUSDT -i 1h -o btc_future.csv --candle-type future
```

---

### 8. import - 导入数据

从文件导入K线数据到数据库。

#### 8.1 import csv - 从CSV导入

```bash
python data_cli.py import csv [INPUT_FILE] [OPTIONS]
```

**位置参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `input_file` | str | CSV文件路径 |

**选项参数：**

| 参数 | 短选项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| `--interval` | `-i` | str | 必需 | 时间周期，如1m, 5m, 1h, 1d |
| `--candle-type` | | str | spot | 蜡烛图类型：spot/future |
| `--batch-size` | `-b` | int | 500 | 批量插入大小 |
| `--skip-validation` | | bool | False | 跳过数据验证 |

**示例：**

```bash
# 导入CSV文件
python data_cli.py import csv data.csv -i 1h

# 导入合约数据
python data_cli.py import csv data.csv -i 1h --candle-type future

# 使用更大的批次导入
python data_cli.py import csv data.csv -i 1h --batch-size 1000

# 跳过数据验证（快速导入）
python data_cli.py import csv data.csv -i 1h --skip-validation
```

---

## 参数说明

### 时间周期（interval）

支持的时间周期格式：

| 格式 | 说明 |
|------|------|
| `1m` | 1分钟 |
| `5m` | 5分钟 |
| `15m` | 15分钟 |
| `30m` | 30分钟 |
| `1h` | 1小时 |
| `4h` | 4小时 |
| `1d` | 1天 |

### 蜡烛图类型（candle-type）

| 类型 | 说明 |
|------|------|
| `spot` | 现货数据 |
| `future` | 合约/期货数据 |

### 下载模式（mode）

| 模式 | 说明 |
|------|------|
| `inc` | 增量模式 - 只下载缺失的数据 |
| `full` | 全量模式 - 重新下载所有数据 |

### 任务状态（status）

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行 |
| `running` | 正在执行 |
| `completed` | 已完成 |
| `failed` | 失败 |

---

## 输入/输出格式

### CSV导出格式

导出的CSV文件包含以下列：

| 列名 | 类型 | 说明 |
|------|------|------|
| `symbol` | str | 交易对，如BTCUSDT |
| `interval` | str | 时间周期，如1h |
| `timestamp` | str | 时间戳（毫秒） |
| `open` | str | 开盘价 |
| `high` | str | 最高价 |
| `low` | str | 最低价 |
| `close` | str | 收盘价 |
| `volume` | str | 成交量 |
| `data_source` | str | 数据源，如binance |

**示例CSV内容：**

```csv
symbol,interval,timestamp,open,high,low,close,volume,data_source
BTCUSDT,1h,1704067200000,42000.00,42500.00,41800.00,42300.00,150.5,binance
BTCUSDT,1h,1704070800000,42300.00,42800.00,42100.00,42600.00,180.3,binance
```

### CSV导入格式

导入的CSV文件**必需**包含以下列：

| 列名 | 类型 | 说明 |
|------|------|------|
| `symbol` | str | 交易对 |
| `timestamp` | int/str | 时间戳 |
| `open` | float/str | 开盘价 |
| `high` | float/str | 最高价 |
| `low` | float/str | 最低价 |
| `close` | float/str | 收盘价 |
| `volume` | float/str | 成交量 |

**可选列：**

| 列名 | 类型 | 说明 |
|------|------|------|
| `interval` | str | 时间周期（如未提供则使用命令行参数） |

**注意事项：**
- 导入的数据会被标记数据源为 `"import"`
- 重复数据会根据 `unique_kline` 字段进行更新
- 支持批量导入以提高性能

---

## 使用示例

### 完整工作流程示例

#### 场景1：下载并查看数据

```bash
# 1. 下载BTCUSDT的1小时数据
python data_cli.py download -s BTCUSDT -i 1h --start 20240101 --end 20241231

# 2. 查看下载任务状态
python data_cli.py list-tasks

# 3. 查看本地数据
python data_cli.py list-local-data -s BTCUSDT

# 4. 导出数据到CSV
python data_cli.py export csv -s BTCUSDT -i 1h -o btc_1h_2024.csv
```

#### 场景2：批量下载多个交易对

```bash
# 下载BTC和ETH的多个时间周期数据
python data_cli.py download \
  -s BTCUSDT -s ETHUSDT \
  -i 1h -i 4h -i 1d \
  --start 20240101 \
  --end 20241231 \
  --max-workers 4

# 监控任务状态
python data_cli.py status -t <task_id> --watch
```

#### 场景3：数据迁移

```bash
# 1. 从数据库A导出数据
python data_cli.py export csv -s BTCUSDT -i 1h -o btc_export.csv

# 2. 将数据导入到数据库B
python data_cli.py import csv btc_export.csv -i 1h
```

#### 场景4：数据清理

```bash
# 1. 查看所有本地数据
python data_cli.py list-local-data

# 2. 删除特定交易对的数据
python data_cli.py delete-local-data -s BTCUSDT -y

# 3. 只删除特定时间周期的数据
python data_cli.py delete-local-data -s BTCUSDT -i 1m -y
```

---

## 错误代码与故障排除

### 退出代码

| 代码 | 含义 |
|------|------|
| `0` | 成功 |
| `1` | 一般错误 |

### 常见错误及解决方案

#### 错误1：模块导入失败

```
错误: 导入模块失败: No module named 'collector'
```

**原因：** 不在正确的目录下运行脚本

**解决方案：**
```bash
# 确保在 backend 目录或其子目录下运行
cd /Users/liupeng/workspace/quant/QuantCell/backend
python scripts/data_cli.py --help
```

#### 错误2：数据库初始化失败

```
错误: 数据库初始化失败
```

**原因：** 数据库配置错误或数据库服务未启动

**解决方案：**
1. 检查数据库配置
2. 确保数据库服务已启动
3. 检查数据库连接字符串

#### 错误3：时间格式错误

```
错误: 时间格式不正确，请使用 YYYYMMDD 格式
```

**解决方案：**
```bash
# 正确格式
--start 20240101

# 错误格式
--start 2024-01-01  # 错误！不要包含分隔符
--start 01/01/2024  # 错误！使用YYYYMMDD格式
```

#### 错误4：CSV文件缺少必需列

```
错误: CSV文件缺少必需列: close, volume
```

**解决方案：**
确保CSV文件包含所有必需列：symbol, timestamp, open, high, low, close, volume

#### 错误5：任务不存在

```
任务 <task_id> 不存在
```

**原因：** 任务ID错误或任务已被清理

**解决方案：**
1. 使用 `list-tasks` 查看有效任务ID
2. 检查任务ID拼写

#### 错误6：文件不存在

```
错误: 文件不存在: data.csv
```

**解决方案：**
```bash
# 使用绝对路径
python data_cli.py import csv /absolute/path/to/data.csv -i 1h

# 或使用相对路径（相对于当前目录）
cd /path/to/csv/files
python data_cli.py import csv data.csv -i 1h
```

### 日志级别

使用 `--verbose` 或 `-v` 启用详细日志：

```bash
python data_cli.py download -s BTCUSDT -i 1d --start 20240101 --end 20241231 -v
```

### 性能优化建议

1. **批量导入**：使用较大的 `--batch-size` 提高导入速度
2. **多线程下载**：使用 `--max-workers` 启用多线程
3. **跳过验证**：导入时添加 `--skip-validation` 跳过数据验证

---

## 附录

### 支持的交易所

当前主要支持：
- **Binance** (币安) - 最完整的支持

### 数据库支持

- **SQLite** - 开发/测试环境
- **DuckDB** - 生产环境（高性能分析）

### 相关文件

| 文件 | 说明 |
|------|------|
| `data_cli.py` | 本CLI工具 |
| `collector/scripts/get_data.py` | 数据获取核心模块 |
| `collector/services/data_service.py` | 数据服务层 |
| `collector/db/models.py` | 数据库模型定义 |

---

*文档版本: 1.0*  
*最后更新: 2026-02-07*  
*QuantCell Project*
