# Scripts CLI 使用手册

## 概述

QuantCell 后端提供了一套命令行工具（CLI），用于管理策略、市场数据、新闻和Web功能。
这些CLI工具可以独立运行，也可以被Agent工具调用。

## CLI模块结构

```
backend/scripts/
├── data_cli.py          # 数据管理
├── backtest_cli.py      # 回测管理
├── worker_cli.py        # Worker管理
├── agent_cli.py         # Agent管理
├── strategy_cli.py      # 策略管理（新增）
├── market_cli.py        # 市场数据（新增）
├── news_cli.py          # 新闻资讯（新增）
└── web_cli.py           # Web工具（新增）
```

---

## strategy_cli.py - 策略管理

### 命令列表

#### list - 列出所有策略
```bash
python scripts/strategy_cli.py list
```

#### info - 查看策略详情
```bash
python scripts/strategy_cli.py info <strategy_id>
# 示例
python scripts/strategy_cli.py info 1
```

#### generate - 生成策略代码
```bash
python scripts/strategy_cli.py generate --requirement "策略需求描述" --name "策略名称"
# 示例
python scripts/strategy_cli.py generate --requirement "双均线交叉策略，快线10日，慢线30日" --name sma_cross
```

#### analyze - 分析回测结果
```bash
python scripts/strategy_cli.py analyze --backtest-id <id>
python scripts/strategy_cli.py analyze --result-file <path>
python scripts/strategy_cli.py analyze --result-data '<json>'
# 示例
python scripts/strategy_cli.py analyze --backtest-id abc123
```

#### optimize - 优化策略参数
```bash
python scripts/strategy_cli.py optimize --strategy-name <name> --param-ranges '<json>'
# 示例
python scripts/strategy_cli.py optimize --strategy-name sma_cross --param-ranges '{"fast": [5,10,15], "slow": [20,30,40]}' --symbols BTCUSDT
```

#### diagnose - 诊断策略问题
```bash
python scripts/strategy_cli.py diagnose --strategy-name <name>
python scripts/strategy_cli.py diagnose --strategy-name <name> --backtest-id <id>
# 示例
python scripts/strategy_cli.py diagnose --strategy-name sma_cross
```

#### deploy - 部署策略到Worker
```bash
python scripts/strategy_cli.py deploy --strategy-name <name> --symbols <symbols>
# 示例
python scripts/strategy_cli.py deploy --strategy-name sma_cross --symbols BTCUSDT,ETHUSDT --exchange binance --auto-start
```

### Python API

```python
from scripts.strategy_cli import list_strategies, get_strategy_detail, generate_strategy

# 列出策略
result = list_strategies()

# 获取策略详情
result = get_strategy_detail(1)

# 生成策略
result = generate_strategy("双均线策略", "sma_cross")
```

---

## market_cli.py - 市场数据

### 命令列表

#### klines - 获取K线数据
```bash
python scripts/market_cli.py klines --symbol <symbol> --timeframe <timeframe>
# 示例
python scripts/market_cli.py klines --symbol BTCUSDT --timeframe 1h --limit 100
```

#### ticker - 获取最新行情
```bash
python scripts/market_cli.py ticker --symbol <symbol>
# 示例
python scripts/market_cli.py ticker --symbol BTCUSDT
```

#### symbols - 获取交易对列表
```bash
python scripts/market_cli.py symbols --exchange <exchange> --filter <filter>
# 示例
python scripts/market_cli.py symbols --exchange binance --filter USDT --limit 50
```

#### fetch - 获取市场数据（综合接口）
```bash
python scripts/market_cli.py fetch --symbol <symbol> --data-type <type>
# 示例
python scripts/market_cli.py fetch --symbol BTCUSDT --data-type kline --interval 1h
python scripts/market_cli.py fetch --symbol BTCUSDT --data-type 24h_ticker
```

### Python API

```python
from scripts.market_cli import get_klines, get_ticker, get_crypto_symbols

# 获取K线数据
result = get_klines("BTCUSDT", "1h", 100, "binance")

# 获取最新行情
result = get_ticker("BTCUSDT", "binance")

# 获取交易对列表
result = get_crypto_symbols("binance", "USDT", 100, "spot")
```

---

## news_cli.py - 新闻资讯

### 命令列表

#### news - 获取财经新闻
```bash
python scripts/news_cli.py news --query <keyword> --count <count>
# 示例
python scripts/news_cli.py news --query bitcoin --count 10
python scripts/news_cli.py news --category business
```

#### sentiment - 获取市场情绪
```bash
python scripts/news_cli.py sentiment
```

### 环境变量

- `NEWSAPI_KEY`: NewsAPI密钥（可选，不配置则返回提示信息）

### Python API

```python
from scripts.news_cli import get_news, get_market_sentiment

# 获取新闻
result = get_news("bitcoin", "business", 10)

# 获取市场情绪
result = get_market_sentiment()
```

---

## web_cli.py - Web工具

### 命令列表

#### search - 搜索网页
```bash
python scripts/web_cli.py search <query> --count <count>
# 示例
python scripts/web_cli.py search "Bitcoin price" --count 5
```

#### fetch - 获取网页内容
```bash
python scripts/web_cli.py fetch <url> --mode <mode> --max-chars <max>
# 示例
python scripts/web_cli.py fetch https://example.com --mode markdown
python scripts/web_cli.py fetch https://example.com --mode text --max-chars 10000
```

### 环境变量

- `BRAVE_API_KEY`: Brave Search API密钥（搜索功能需要）
- `HTTP_PROXY` / `HTTPS_PROXY`: 代理地址（可选）

### Python API

```python
from scripts.web_cli import web_search, web_fetch

# 搜索网页
result = web_search("Bitcoin price", count=5, api_key="your_key")

# 获取网页内容
result = web_fetch("https://example.com", extract_mode="markdown", max_chars=50000)
```

---

## 架构说明

### 分层架构

```
┌─────────────────────────────────────┐
│  Agent Tools (薄封装)               │  ← agent/tools/trading/*.py
├─────────────────────────────────────┤
│  CLI层 (薄封装)                     │  ← scripts/*_cli.py
├─────────────────────────────────────┤
│  Service层 (业务逻辑)               │  ← strategy/service.py, collector/services/*.py
├─────────────────────────────────────┤
│  Repository层 (数据访问)            │  ← collector/db/models.py
└─────────────────────────────────────┘
```

### 设计原则

1. **CLI层是薄封装**：直接调用Service层，不包含业务逻辑
2. **Agent工具调用CLI**：Agent工具的execute方法调用CLI函数
3. **统一返回字符串**：CLI函数统一返回字符串结果或错误信息
4. **错误处理**：错误信息以"错误:"开头，不抛出异常

### 添加新CLI

1. 在 `scripts/` 目录创建新的CLI文件
2. 实现核心函数（返回字符串）
3. 添加Typer命令装饰器
4. 创建对应的Agent工具类（调用CLI函数）
5. 编写单元测试

---

## 测试

### 运行所有CLI测试

```bash
cd backend
python -m pytest tests/unit/scripts/ -v
```

### 运行特定CLI测试

```bash
python -m pytest tests/unit/scripts/test_strategy_cli.py -v
python -m pytest tests/unit/scripts/test_market_cli.py -v
python -m pytest tests/unit/scripts/test_news_cli.py -v
python -m pytest tests/unit/scripts/test_web_cli.py -v
```

### 测试覆盖率

```bash
python -m pytest tests/unit/scripts/ --cov=scripts --cov-report=html
```
