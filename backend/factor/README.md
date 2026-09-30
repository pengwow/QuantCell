# 因子计算模块 (Factor Module)

## 概述

因子计算模块提供量化交易因子计算和管理功能，支持多种类型的因子计算和分析。

## 功能特性

- **因子管理**：获取、添加、删除自定义因子（表达式因子 + 代码因子双轨）
- **因子计算**：支持单因子、多因子、所有因子计算
- **因子分析**：IC分析、IR分析、分组分析、单调性检验、稳定性检验
- **因子验证**：验证因子表达式有效性
- **代码因子（LLM 挖掘 + 沙箱）**：LLM 生成 pandas 代码 → 进程级沙箱执行 → 复用同一套 IC/Inspector 指标评估 → 反思迭代 → 优秀代码入库

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

### 财务因子（当前加密行情数据源不支持，仅占位，`supported=False`）
- `pe`: 市盈率
- `pb`: 市净率
- `roe`: 净资产收益率
- `roa`: 总资产收益率
- `profit_growth`: 利润增长率

## 目录结构

```
factor/
├── __init__.py          # 模块导出
├── README.md            # 模块文档
├── engine.py            # pandas 自有表达式引擎（AST 白名单求值）
├── factor_store.py      # 表达式因子 JSON 持久化（custom_factors.json）
├── code_store.py        # 代码因子 JSON 持久化（code_factors.json）
├── sandbox.py           # LLM 代码沙箱（AST 白名单 + 子进程编排 + 输出契约）
├── sandbox_runner.py    # 沙箱子进程入口（仅 stdlib+numpy/pandas，禁 import factor 包）
├── llm_miner.py         # LLM 挖掘闭环（生成→沙箱→评估→反思）
├── job_manager.py       # 异步任务（analyze/compare/llm_mine）+ WS 进度
├── routes.py            # API路由
├── schemas.py           # Pydantic模型
└── service.py           # 业务服务（_analyze_core 为分析/挖掘共用指标口径）

# 单元测试位于 tests/unit/factor/
#   test_factor_engine.py / test_factor_store.py / test_factor_analyze.py
```

## API端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/factor/list` | 获取因子名称列表 |
| GET | `/api/v1/factor/list-detail` | 获取因子明细列表（分类/表达式/可计算） |
| GET | `/api/v1/factor/expression/{name}` | 获取因子表达式 |
| GET | `/api/v1/factor/instruments` | 获取可分析品种与可用周期 |
| POST | `/api/v1/factor/add` | 添加自定义因子 |
| DELETE | `/api/v1/factor/delete/{name}` | 删除自定义因子 |
| POST | `/api/v1/factor/calculate` | 计算单因子 |
| POST | `/api/v1/factor/calculate-multi` | 计算多因子 |
| POST | `/api/v1/factor/calculate-all` | 计算所有可计算因子 |
| POST | `/api/v1/factor/analyze` | 一站式因子分析（IC/IR/分组/单调性/稳定性） |
| POST | `/api/v1/factor/validate` | 验证因子表达式 |
| POST | `/api/v1/factor/correlation` | 计算因子相关性 |
| POST | `/api/v1/factor/stats` | 获取因子统计 |
| POST | `/api/v1/factor/ic` | 计算IC |
| POST | `/api/v1/factor/ir` | 计算IR |
| POST | `/api/v1/factor/group-analysis` | 分组分析 |
| POST | `/api/v1/factor/monotonicity` | 单调性检验 |
| POST | `/api/v1/factor/stability` | 稳定性检验 |
| POST | `/api/v1/factor/code/validate` | 校验代码因子（静态策略 + 合成数据沙箱真实执行） |
| POST | `/api/v1/factor/code/add` | 新增代码因子（沙箱校验通过后入库） |
| DELETE | `/api/v1/factor/code/{name}` | 删除代码因子 |
| POST | `/api/v1/factor/mine/llm` | 提交 LLM 因子挖掘异步任务（job 进度走 WS `factor:job`，结果走 `/jobs/{id}/result`） |

## 代码因子沙箱安全模型

LLM 生成的代码不可信，执行边界为三层防线（研究级防护，非多租户安全边界）：

1. **静态 AST 白名单**（`FactorCodePolicy`，父进程执行）：只允许向量化表达式节点；禁 `import`、dunder、属性/名称白名单之外的访问、`**kwargs`、列表推导/lambda/循环/with/类定义；必须把结果赋给 `factor`。
2. **独立子进程 + 资源限额**（`sandbox_runner.py`）：按文件路径启动（不经过 factor 包重依赖链），受限 builtins（无 open/exec/eval/__import__）；rlimit 限制 CPU 秒数、虚拟内存、FD 数；wall-clock 超时由父进程强杀；stdin/stdout 长度帧 pickle 通信。macOS 不强制 `RLIMIT_AS`，runner 另以峰值 RSS（`ru_maxrss`）事后兜底。
3. **输出契约**：`factor` 必须是与 `df` 等长、索引逐行对齐、无重复索引、数值型、至少一个有限值且不含 inf 的 `pandas.Series`。

已知上限与升级路径：无内核级网络/文件系统隔离（网络阻断靠「禁 import + FD 限额」、文件访问靠「无 open」）；升级路径为 macOS `sandbox-exec` / Linux bubblewrap 包装 runner。挖掘当前为单面板 in-sample 选因子，升级路径为 train/test 切分 + walk-forward 复核。

## 使用示例

### 获取因子列表

```python
from factor import FactorService

service = FactorService()
factors = service.get_factor_list()
print(factors)
```

### 计算单因子

```python
from factor import FactorService

service = FactorService()
result = service.calculate_factor(
    factor_name="momentum_5d",
    instruments=["BTCUSDT", "ETHUSDT"],
    start_time=None,
    end_time=None,
    interval="1h",
    candle_type="spot",
)
print(result)
```

### 添加自定义因子

```python
from factor import FactorService

service = FactorService()
service.add_factor(
    factor_name="my_factor",
    factor_expression="close - open",
)
```

## 依赖

- pandas: 数据处理
- numpy: 数值计算
- scipy: 科学计算
- 本地 parquet K 线数据（`backend/data/source/crypto/...`，由 quality.parquet_provider 读取）

## 作者

QuantCell Team

## 版本

1.0.0
