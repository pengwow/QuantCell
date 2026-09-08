# QuantCell — AI 原生量化交易系统

[Demo 地址](https://demo.quantcell.top/chart) | [项目主页](https://quantcell.top)

## 项目简介

QuantCell 是一款 AI 原生的量化交易系统，以 `axon-quant`（Rust 核心）为交易引擎，以 FastAPI 为服务框架、React + TypeScript 为前端，提供从策略开发、回测验证到实盘部署的全流程能力。

核心设计理念：**让量化交易变得简单、高效、智能**——自然语言即可描述策略，AI 自动生成代码并完成回测验证。

## 核心特性

### 🤖 AI 智能

- **自然语言策略生成**：中文描述交易想法，AI 自动生成可执行策略代码
- **思维链推理**：多步骤策略生成与指标生成，逻辑可解释、可追溯
- **代码质量自检**：自动校验语法与运行时安全，拒绝不安全代码
- **智能 Agent**：具备记忆与工具调用能力的 AI Agent，可进行多轮对话与操作编排

### ⚡ Axon-Quant 高性能引擎

- **Rust 核心驱动**：底层采用 `axon-quant 0.11.1`，事件驱动架构
- **多数据源回测**：支持 K 线、Tick、衍生数据（Deriv）、OrderBook 等数据适配器
- **Walk-Forward 验证**：滚动窗口回测，防止过拟合
- **HPO 超参优化**：内置超参数优化框架

### 🎯 强化学习

- **Gymnasium 量化环境**：内置交易 Gym 环境
- **Stable-Baselines3**：支持 PPO / SAC / DQN 等主流算法
- **完整生命周期**：训练 → 回测 → 评估，支持 Walk-Forward 验证

### 🔌 插件系统

- **插件安装与管理**：通过 `quantcell plugin` 命令安装、打包、管理插件
- **事件总线**：插件间通过统一事件总线通信
- **安全沙箱**：插件在受限沙箱中运行，保障主进程安全

### 🛡️ 风控与合规

- **凭证加密存储**：交易所 API 密钥加密入库，`quantcell account` 统一管理
- **风险引擎**：交易风险指标监控、止损与持仓风控
- **多语言界面**：内置 i18n 国际化

### 📊 完整数据生态

- **多交易所**：Binance（实盘 / 纸面 / 归档）、OKX 适配器
- **实时行情**：WebSocket 实时订阅、分发与持久化
- **Parquet 存储**：列式存储，高效读写
- **数据质量检测**：缺失值检测、自动回补与归档修复

### 🎨 现代化前端

- **React 18 + TypeScript + Vite**：类型安全的组件化开发
- **Ant Design 6**：企业级 UI 组件库
- **KLineCharts / ECharts**：专业级 K 线与指标图表
- **Zustand + Immer**：轻量高效的全局状态
- **i18n 国际化**：中英文无缝切换（i18next）
- **Monaco 编辑器**：内置代码编辑器

## 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                    前端 (React + TypeScript)               │
│        Ant Design 6 · KLineCharts · Zustand · i18n        │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼───────────────────────────────┐
│                 API Layer (FastAPI)                       │
│   CORS · JWT 校验 · 异常处理 · 多组业务路由 · /ws/worker      │
└──────┬───────────────┬────────────────┬───────────────────┘
       │               │                │
       ▼               ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ 策略与回测    │  │ 实时交易     │  │ 数据采集     │
│ strategy/   │  │ realtime/   │  │ collector/  │
│ backtest/   │  │ engine/     │  │ quality/    │
│ rl / factor │  │ worker/     │  │ model/      │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────────────────────────────────────────────────┐
│   axon-quant (Rust) · Binance / OKX · DuckDB + Parquet   │
└──────────────────────────────────────────────────────────┘
       ▲                ▲                ▲
┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
│   Agent     │  │   CLI       │  │   插件      │
│  agent/     │  │  quantcell  │  │  plugins/   │
│  ai_model/  │  │  13 组命令   │  │  事件总线    │
└─────────────┘  └─────────────┘  └─────────────┘
```

## 技术栈

| 类别 | 技术 |
|------|------|
| 后端语言 | Python 3.14 |
| Web 框架 | FastAPI 0.136（uvicorn） |
| 交易引擎 | axon-quant 0.11.1（Rust 核心） |
| 数据库 | DuckDB 1.4 + Parquet + SQLAlchemy 2 + Alembic |
| 数据处理 | Pandas 2.3 / PyArrow 22 |
| 强化学习 | Gymnasium 1.3 + Stable-Baselines3 2.9 |
| 命令行 | Typer 0.20 |
| 前端框架 | React 18 + TypeScript + Vite 7 |
| UI 组件 | Ant Design 6 + TailwindCSS 4 |
| 图表 | KLineCharts 10 + ECharts 5.5 |
| 状态管理 | Zustand 5 + Immer |
| 国际化 | i18next / react-i18next |
| 包管理 | uv（后端）/ bun（前端） |
| 代码规范 | ruff（lint + format） |
| 测试 | pytest 9 + coverage（覆盖率基线 57%） |

## 项目结构

```
QuantCell/
├── backend/                          # FastAPI 后端
│   ├── main.py                        # 应用入口（路由注册、CORS、异常处理）
│   ├── pyproject.toml                 # 依赖与 quantcell CLI 入口（uv 管理）
│   ├── init_db.py / run_migrations.py # 数据库初始化和迁移
│   ├── alembic/                       # 数据库迁移脚本
│   ├── agent/                         # AI Agent（会话、技能、工具、API）
│   ├── ai_model/                      # 策略生成（思维链、代码校验、模板库）
│   ├── api/                           # 服务路由（模型注册/集成/风控/RL）
│   ├── axon_bridge/                   # axon-quant 桥接层
│   ├── backtest/                      # 回测（事件驱动、HPO、滚动验证）
│   ├── cli/                           # quantcell 命令 (13 组)
│   ├── collector/                     # 数据采集（K线/衍生/归档/质量）
│   ├── common/                        # 公共服务（通知等）
│   ├── core/                          # 生命周期、端口管理、调度器
│   ├── credentials/                   # 账户凭证加密存储
│   ├── engine/                        # 交易引擎与部署
│   ├── exchange/                      # 交易所适配（Binance/OKX）
│   ├── factor/ indicators/ model/     # 因子/指标计算/模型服务
│   ├── plugins/                       # 插件系统（事件总线、沙箱、API）
│   ├── realtime/                      # 实时行情引擎
│   ├── rl/                            # 强化学习（训练/评估/滚动验证）
│   ├── services/                      # 业务服务层（风控/OMS/集成）
│   ├── settings/                      # 系统设置与配置 API
│   ├── share/                         # 分享系统
│   ├── strategy/                      # 策略系统（模板/循环/实盘）
│   ├── websocket/                     # WebSocket 路由
│   ├── worker/                        # Worker 系统（实盘执行）
│   └── tests/                         # 单元与集成测试
├── frontend/                          # React 前端（Vite + antd 6）
├── docs/                              # 技术文档
├── scripts/                           # 辅助脚本
├── ui/                                # 微前端壳
├── i18n/                              # 国际化资源
├── logs/                              # 运行日志
├── agent_workspace/                   # Agent 工作区
├── install.sh                         # 一键安装脚本
└── README.md                          # 本文件
```

## 快速开始

### 环境要求

| 组件 | 版本 |
|------|------|
| Python | 3.14 |
| Node.js | 18+ |
| uv | latest |
| bun | latest |

### 一键安装

```bash
git clone https://github.com/pengwow/quantcell.git
cd quantcell
bash install.sh
```

`install.sh` 支持 `--minimal` / `--full` / `--extra` 安装模式，并自动处理 uv、bun 工具链与前后端环境。

### 手动安装

**后端**

```bash
cd backend
uv sync                       # 安装依赖并生成 quantcell CLI 入口
python init_db.py             # 初始化数据库
```

**前端**

```bash
cd frontend
bun install
```

### 启动服务

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

访问接口文档：`http://localhost:8000/docs`

前端（开发模式）：

```bash
cd frontend
bun run dev
```

## CLI 使用

安装后（`uv sync`）即生成 `quantcell` 命令，共 13 组子命令：

```
$ quantcell --help
 Usage: quantcell [OPTIONS] COMMAND [ARGS]...

 QuantCell 命令行工具

 Commands:
   agent       Agent 管理命令行工具
   market      市场数据命令行工具
   news        新闻与市场情绪工具
   plugin      插件管理命令行工具
   rl          RL 命令行工具
   web         Web 搜索与抓取工具
   worker      Worker 管理命令行工具
   tests       QuantCell 测试运行脚本
   account     凭证管理（add/list/remove）
   migrate     数据库迁移(SQLite schema 升级)
   strategy    策略管理命令行工具
   backtest    QuantCell 回测工具（事件驱动引擎 axon-quant）
   data        数据管理命令行工具
```

> 安装完成后（`uv sync`），`quantcell` 可执行文件即生成于 Python 环境 bin 目录（如 `backend/.venv/bin/quantcell`），可直接在任意目录使用，例如 `quantcell --help`。

### 命令速查

| 任务 | 命令 |
|------|------|
| 列出策略 | `quantcell strategy list` |
| AI 生成策略 | `quantcell strategy generate --requirement "双均线金叉买入" --name my_strategy` |
| 运行回测 | `quantcell backtest run --symbols BTCUSDT --timeframes 1h --initial-capital 100000` |
| 下载行情数据 | `quantcell data download --symbol BTCUSDT --interval 1d` |
| 数据质量检查 | `quantcell data quality check --start 20240101 --end 20241231` |
| 从 CSV 导入数据 | `quantcell data import csv <文件路径>` |
| 查看市场行情 | `quantcell market fetch --symbol BTCUSDT --interval 1h` |
| 训练 RL 模型 | `quantcell rl train --symbol BTCUSDT --algorithm ppo --timesteps 100000` |
| 启动 Worker | `quantcell worker start <worker_id>` |
| 查看 Worker | `quantcell worker list-workers` |
| 查看账户 | `quantcell account list` |
| 迁移数据库 | `quantcell migrate -y` |
| 跑单元测试 | `quantcell tests main --unit` |
| 安装插件 | `quantcell plugin install x.zip` |

## 核心功能使用

### 1. AI 生成策略

在【前端对话界面】输入，或在命令行直接生成：

```bash
quantcell strategy generate \
  --requirement "基于双均线的趋势跟踪策略，快线 10 天、慢线 30 天，金叉买入、死叉卖出" \
  --name dual_ma
```

系统自动完成：理解需求 → 生成代码 → 安全校验 → 回测验证 → 输出报告。

### 2. 运行回测

```bash
quantcell backtest run \
  --symbols BTCUSDT \
  --timeframes 1h \
  --initial-capital 100000
```

Python 方式（详细用法见 [backend/backtest/README.md](backend/backtest/README.md)）：

```python
from backtest.engine_service import BacktestEngine
from backtest.data_provider import BacktestDataProvider

provider = BacktestDataProvider()          # 数据提供者（Parquet/CSV）
engine = BacktestEngine(data_provider=provider)
result = engine.run_backtest(
    strategy_name="dual_ma",
    strategy_params={"fast": 10, "slow": 30},
    symbols=["BTCUSDT"],
    timeframes=["1h"],
    data_type="kline",
    market="spot",
)
print(result)  # 返回含收益率/最大回撤/成交记录等指标的 dict
```

### 3. 强化学习训练

```bash
quantcell rl train \
    --symbol BTCUSDT \
    --algorithm ppo \
    --timesteps 100000 \
    --reward sharpe

# 一键生命周期: 训练 → 回测 → 评估 → 重训练
quantcell rl lifecycle --symbol BTCUSDT --train-steps 30000 --retrain-steps 10000
```

### 4. 策略模板

项目内置多种策略模板（`backend/strategy/templates/`），可直接使用或作为开发参考：

| 模板 | 说明 |
|------|------|
| `dual_ma.py` | 双均线交叉策略 |
| `sma_crossover.py` | SMA 交叉策略 |
| `grid.py` | 网格交易策略 |
| `mean_reversion.py` | 均值回归策略 |
| `momentum.py` | 动量策略 |
| `trend_follow.py` | 趋势跟踪策略 |
| `cross_sectional.py` | 截面策略 |
| `llm_signal.py` | LLM 信号策略 |
| `funding_arbitrage.py` | 资金费率套利 |
| `mean_reversion_rl.py` | 强化学习均值回归 |

### 5. 插件开发

```python
from plugins.plugin_base import PluginBase

class MyPlugin(PluginBase):
    name = "my-plugin"
    version = "1.0.0"

    def on_load(self):
        self.event_bus.subscribe("strategy:created", self.handle_strategy_created)

    def handle_strategy_created(self, event):
        pass
```

打包并安装：

```bash
quantcell plugin pack ./my-plugin
quantcell plugin install my-plugin.zip
```

## API 概览

后端服务启动后，访问：

- **Swagger UI**：`http://localhost:8000/docs`
- **ReDoc**：`http://localhost:8000/redoc`
- **健康检查**：`http://localhost:8000/health`

### 主要路由组

| 前缀 | 说明 |
|------|------|
| `/api/strategy` | 策略 CRUD / 生成 / 部署 |
| `/api/backtest` | 回测执行与结果 |
| `/api/agent` | AI Agent 对话与操作 |
| `/api/ai-models` | AI 模型与策略生成 API |
| `/api/model` | 模型服务 |
| `/api/factor` / `/api/indicators` | 因子分析 / 指标计算 |
| `/api/data`、`/api/data/deriv`、`/api/data/archive` | 数据采集（K线/衍生/归档） |
| `/api/quality` | 数据质量与管理 |
| `/api/exchanges` | 交易所连接管理 |
| `/api/realtime` | 实时行情引擎 |
| `/api/engine` | 交易引擎 / 部署 |
| `/api/workers` | Worker 管理 |
| `/api/plugins` | 插件管理 |
| `/api/settings` / `/api/config` | 系统设置 / 配置 |
| `/api/notifications` | 通知中心 |
| `/api/logs` | 日志查询 |
| `/api/system` | 系统信息与端口 |
| `/api/share` | 分享系统 |
| `/api/models` `/api/risk` `/api/ensemble` `/api/rl` | 模型注册 / 风控 / 集成 / RL 训练 |
| `/ws/worker` | Worker WebSocket |

## 测试与覆盖率

```bash
cd backend

# 单元测试
.venv/bin/python -m pytest tests/unit/ -v

# 集成测试
.venv/bin/python -m pytest tests/integration/ -v

# 或者使用 CLI
quantcell tests main --unit
quantcell tests main --integration
```

覆盖率基线：`pyproject.toml` 中 `fail_under = 57`——作为防回归门槛，新增代码应逐步提高覆盖率。

## 开发指南

### 新增策略

1. 在 `backend/strategy/templates/` 创建策略模板（参考 `dual_ma.py`）
2. 或直接创建新策略文件（如 `backend/strategies/my_strategy.py`），实现 `on_bar()`
3. 用 `quantcell backtest run` 验证

### 新增后端 API

1. 在 `backend/<module>/routes.py` 中定义 `APIRouter`
2. 在 `backend/main.py` 中注册
3. 业务逻辑放 Service 层，路由层只接收参数调 Service
4. 参数校验交 Pydantic Schema
5. 编写单元测试和集成测试

### 新增 CLI 子命令

1. 在 `backend/cli/<name>.py` 定义 `app = typer.Typer(...)` 及其命令
2. 在 `backend/cli/__init__.py` 的 `register_commands()` 中注册子命令
3. `uv sync` 后即可使用

### 代码规范

项目使用 ruff（lint + format）：

```bash
# 检查
ruff check backend/

# 自动修复
ruff check backend/ --fix

# 格式化
ruff format backend/
```

优雅地使用结构化日志：统一通过 `backend/utils/logger.py` 记录，不要使用 `print`。

## 常见问题

### Q: 启动时提示端口被占用？
系统集成了 `PortManager`，默认自动分配可用端口。也可通过 `--port` 参数手动指定。

### Q: 如何配置交易所 API？
通过前端「设置 → 交易所」页面配置，或在 `backend/config/binance_example.yaml` 中配置。API 密钥使用 `backend/credentials/` 模块加密存储。

### Q: 回测结果不准确？
检查：1) 数据完整性（`quantcell data quality check`）2) 用 Walk-Forward 验证 3) 尝试多数据源（`data_type` / `market` 参数）。

### Q: 如何开启调试模式？

```bash
# Web 服务
uvicorn main:app --reload

# CLI
LOG_LEVEL=DEBUG quantcell backtest run ...
```

### Q: 时间戳单位不一致怎么办？
`utils/timestamp_utils.py` 提供统一的时间戳处理工具：
- `convert_to_datetime()` — 自动检测 µs/ms/ns 单位
- `normalize_timestamp_column()` — 统一时间列名为 `timestamp`
- `validate_timestamp_column()` — 校验时间列完整性

### Q: Parquet 文件损坏如何恢复？
系统会自动将损坏的 `.parquet` 文件归档为 `.bak` 并重新下载。手动恢复可查看 `quantcell data archive --help` 相关命令。

## 贡献指南

1. Fork 项目到自己的账号
2. 创建功能分支：`git checkout -b feat/amazing-feature`
3. 提交代码：`git commit -m 'feat: add amazing feature'`
4. 运行测试：`quantcell tests main`
5. 推送分支并创建 Pull Request

## 许可证

本项目采用 Apache License 2.0。详见 [LICENSE](LICENSE) 文件。

## 联系方式

- **项目主页**：[https://quantcell.top](https://quantcell.top)
- **Demo**：[https://demo.quantcell.top/chart](https://demo.quantcell.top/chart)
- **邮箱**：<pengwow@hotmail.com>

---

**QuantCell** — AI 原生量化交易系统，让量化交易更简单、更高效、更智能。