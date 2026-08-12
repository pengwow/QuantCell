# QuantCell — AI 原生量化交易系统

[Demo 地址](https://demo.quantcell.top/chart) | [项目主页](https://quantcell.top)

## 项目简介

QuantCell 是一款 AI 原生的量化交易系统，以 `axon-quant`（Rust 核心）为交易引擎，以 FastAPI 为服务框架，以 React + TypeScript 为前端，提供从策略开发、回测验证到实盘部署的全流程能力。

核心设计理念：**让量化交易变得简单、高效、智能**——自然语言即可描述策略，AI 自动生成代码并完成回测验证。

## 核心特性

### 🤖 AI 智能
- **自然语言策略生成**：中文描述交易想法，AI 自动生成可执行策略代码
- **思维链推理**：多步骤策略生成，逻辑可解释、可追溯
- **代码质量自检**：自动校验语法与运行时安全，拒绝不安全代码
- **智能 Agent**：具备长期记忆的 AI Agent，可进行多轮对话与操作编排

### ⚡ Axon-Quant 高性能引擎
- **Rust 核心驱动**：底层采用 `axon-quant 0.10.0`，事件驱动架构
- **多数据源回测**：支持 K 线、Tick、衍生数据（Deriv）等多类型数据源
- **Walk-Forward 验证**：滚动窗口回测，防止过拟合
- **HPO 超参优化**：内置超参数优化框架

### 🎯 强化学习
- **Gymnasium 环境**：内置量化交易 Gym 环境
- **Stable-Baselines3**：支持 PPO、DQN 等主流强化学习算法
- **RL 策略模板**：`mean_reversion_rl.py` 开箱即用

### 🔌 插件系统
- **插件安装/管理**：通过 `quantcell plugin` 命令安装和管理插件
- **事件总线**：插件间通过统一事件总线通信
- **安全沙箱**：插件在受限沙箱中运行，保障主进程安全

### 🛡️ 风控与合规
- **JWT 认证**：所有 API 接口统一 JWT 认证
- **风险引擎**：实时风险指标监控与告警
- **多账户凭证管理**：加密存储交易所 API 密钥
- **RBAC 权限控制**：基于角色的访问控制

### 📊 完整数据生态
- **多交易所**：Binance、OKX 原生适配器
- **实时行情**：WebSocket 实时订阅与分发
- **Parquet 存储**：列式存储，高效读写
- **数据质量检测**：缺失值检测与自动回补

### 🎨 现代化前端
- **React 18 + TypeScript**：类型安全的组件化开发
- **Ant Design 6**：企业级 UI 组件库
- **Zustand 状态管理**：轻量高效的全局状态
- **i18n 国际化**：中英文无缝切换
- **Monaco 编辑器**：内置代码编辑器
- **KLineCharts 图表**：专业级 K 线与指标图表

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                  前端 (React + TypeScript)                │
│              Ant Design 6 · Zustand · i18n                │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────────┐
│                  API Layer (FastAPI)                      │
│    JWT 认证 · 路由分发 · 异常处理 · CORS                   │
└───────┬────────────────┬────────────────┬───────────────┘
        │                │                │
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  StrategyLoop│ │ BacktestLoop │ │  RL Service  │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│          TradingEngine (核心单例) · axon-quant 0.10.0     │
│  Exchange Adapter · Risk Engine · OMS · Plugin Bus        │
└─────────────────────────────────────────────────────────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Binance     │ │    OKX       │ │   DuckDB     │
│  (Paper/Live) │ │   (Live)     │ │  (Parquet)   │
└──────────────┘ └──────────────┘ └──────────────┘
```

## 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.14 | 后端主语言 |
| 语言 | TypeScript | 前端主语言 |
| 交易引擎 | axon-quant 0.10.0 | Rust 核心，事件驱动 |
| Web 框架 | FastAPI 0.136 | 异步 API 服务 |
| 数据库 | DuckDB + SQLAlchemy | 列式分析 + 关系存储 |
| 包管理 | uv / bun | 后端 / 前端 |
| 前端框架 | React 18 + Ant Design 6 | UI 开发 |
| 状态管理 | Zustand | 轻量全局状态 |
| 强化学习 | Gymnasium + Stable-Baselines3 | RL 训练与推理 |
| 认证 | PyJWT + bcrypt | JWT + 密码哈希 |
| 任务调度 | APScheduler | 定时任务 |
| 数据处理 | Pandas / PyArrow | 数据读写 |
| 行情数据 | python-binance / ccxt | 交易所 SDK |

## 项目结构

```
QuantCell/
├── backend/                          # 后端主目录
│   ├── main.py                       # FastAPI 入口
│   ├── pyproject.toml                # 项目依赖 (uv 管理)
│   │   ├── agent/                    # AI Agent 模块
│   │   │   ├── core/                 #   DecisionAgent / InteractionAgent
│   │   │   ├── skills/               #   Agent 技能系统
│   │   │   ├── tools/                #   交易工具集
│   │   │   └── session/              #   会话管理
│   │   ├── ai_model/                 # AI 模型服务
│   │   │   ├── strategy_generator.py #   策略生成器
│   │   │   ├── thinking_chain.py     #   思维链推理
│   │   │   └── code_validator.py     #   代码安全校验
│   │   ├── api/                      # API 路由
│   │   │   └── v2/                   #   V2 API (模型/集成/风控/RL)
│   │   ├── axon_bridge/              # Axon-Quant 桥接层
│   │   │   ├── _async.py             #   异步桥接
│   │   │   ├── _credentials.py       #   凭证桥接
│   │   │   ├── data/ oms/ risk/ rl/  #   领域桥接
│   │   │   └── ensemble/ inference/  #   高级能力桥接
│   │   ├── backtest/                 # 回测系统
│   │   │   ├── engines/              #   回测引擎
│   │   │   ├── data_adapters/        #   数据源适配器 (K线/Tick/Deriv)
│   │   │   ├── hpo_runner.py         #   超参优化
│   │   │   ├── walk_forward.py       #   Walk-Forward 验证
│   │   │   └── baseline.py           #   基准回测
│   │   ├── cli/                      # CLI 命令行 (quantcell)
│   │   │   ├── run.py                #   入口
│   │   │   ├── strategy.py           #   策略命令
│   │   │   ├── backtest.py           #   回测命令
│   │   │   ├── rl.py                 #   RL 命令
│   │   │   └── plugin.py             #   插件命令
│   │   ├── collector/                # 数据采集
│   │   ├── credentials/              # 凭证管理 (JWT/加密存储)
│   │   ├── engine/                   # 交易引擎封装
│   │   ├── exchange/                 # 交易所接口
│   │   │   ├── binance/              #   Binance (实盘 + 纸面)
│   │   │   └── okx/                  #   OKX
│   │   ├── plugins/                  # 插件系统
│   │   ├── rl/                       # 强化学习
│   │   │   ├── env.py                #   Gym 环境
│   │   │   ├── hpo.py                #   超参优化
│   │   │   ├── walk_forward_rl.py    #   滚动验证
│   │   │   └── rewards.py           #   奖励函数
│   │   ├── strategy/                 # 策略系统
│   │   │   ├── templates/            #   内置策略模板
│   │   │   └── core/                 #   核心组件
│   │   ├── realtime/                 # 实时数据
│   │   ├── share/                    # 分享系统
│   │   ├── services/                 # 业务服务层
│   │   ├── tests/                    # 测试代码
│   │   └── utils/                    # 工具函数
├── frontend/                         # 前端主目录
│   ├── src/
│   │   ├── pages/                    # 页面组件
│   │   ├── components/               # 通用组件
│   │   ├── api/                      # API 调用封装
│   │   ├── store/                    # Zustand 状态
│   │   └── router/                   # 路由配置
│   └── package.json                  # 前端依赖 (bun 管理)
├── ui/                               # 微前端壳
├── data/                             # 行情数据 (Parquet)
├── docs/                             # 文档
├── install.sh                        # 一键安装脚本
├── AGENTS.md                         # Agent 行为规范
├── CODE_WIKI.md                      # 代码 Wiki
└── README.md                         # 本文件
```

## 快速开始

### 环境要求

| 组件 | 最低版本 |
|------|---------|
| Python | 3.14 |
| uv | latest |
| Node.js | 18+ |
| bun | latest |

### 一键安装

```bash
git clone https://github.com/pengwow/quantcell.git
cd quantcell
bash install.sh
```

### 手动安装

**后端**

```bash
cd backend
uv sync
uv pip install -e .       # 注册 quantcell CLI
python init_db.py          # 初始化数据库
```

**前端**

```bash
cd frontend
bun install
```

### 启动服务

**方式一：Web 服务模式**

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

访问 API 文档：`http://localhost:8000/docs`

**方式二：CLI 模式**

```bash
# 启动 Web 服务
quantcell web start

# 仅跑回测
quantcell backtest run --strategy dual_ma --symbol BTCUSDT --from 2024-01-01 --to 2024-12-31

# 训练强化学习模型
quantcell rl train --symbol BTCUSDT --timesteps 100000

# 启动 Worker
quantcell worker start <worker_id>
```

### 三种等价的 CLI 入口

```bash
# 推荐：安装后使用
quantcell strategy list

# 不安装，直接调用
python -m cli.run strategy list

# 兼容期内仍可用旧脚本 (将在 6 个月后废弃)
python scripts/strategy_cli.py list
```

## 核心功能使用

### 1. AI 生成策略

在前端对话界面输入：

```
帮我生成一个基于双均线的交易策略，快线 10 天，慢线 20 天，金叉买入，死叉卖出。
```

系统自动完成：理解需求 → 生成代码 → 安全校验 → 回测验证 → 输出报告。

### 2. 运行回测

```python
from backtest.engine_service import BacktestEngine

engine = BacktestEngine()
result = engine.run_backtest(
    strategy_name="dual_ma",
    initial_capital=100000,
    start_date="2024-01-01",
    end_date="2024-12-31",
    symbols=["BTCUSDT"],
    data_sources=["kline", "deriv"],  # 多数据源
)

print(f"收益率: {result.total_return:.2f}%")
print(f"最大回撤: {result.max_drawdown:.2f}%")
```

### 3. 强化学习训练

```bash
quantcell rl train \
    --symbol BTCUSDT \
    --timesteps 100000 \
    --algorithm PPO \
    --seed 42

# 滚动验证
quantcell rl walk-forward \
    --symbol BTCUSDT \
    --windows 5 \
    --window-size 90
```

### 4. 策略模板

项目内置多种策略模板，可直接使用或作为开发参考：

| 模板 | 说明 |
|------|------|
| `dual_ma.py` | 双均线交叉策略 |
| `sma_crossover.py` | SMA 交叉策略 |
| `grid.py` | 网格交易策略 |
| `mean_reversion.py` | 均值回归策略 |
| `momentum.py` | 动量策略 |
| `trend_follow.py` | 趋势跟踪策略 |
| `funding_arbitrage.py` | 资金费率套利 |
| `cross_sectional.py` | 截面策略 |
| `llm_signal.py` | LLM 信号策略 |
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

```bash
quantcell plugin install --zip my-plugin.zip
```

## CLI 命令速查

| 任务 | 命令 |
|------|------|
| 启动 Web 服务 | `quantcell web start` |
| 列出策略 | `quantcell strategy list` |
| 启动回测 | `quantcell backtest run ...` |
| 训练 RL | `quantcell rl train --symbol BTCUSDT` |
| 启动 Worker | `quantcell worker start <id>` |
| 安装插件 | `quantcell plugin install --zip x.zip` |
| 跑测试 | `quantcell tests main --unit` |
| 迁移数据库 | `quantcell migrate run -y` |
| 拉行情 | `quantcell market klines --symbol BTCUSDT` |
| 下载数据 | `quantcell data download -s BTCUSDT -i 1d` |
| AI 对话 | `quantcell agent chat send "Hello"` |

## API 概览

后端服务启动后，访问以下地址：

- **Swagger UI**：`http://localhost:8000/docs`
- **ReDoc**：`http://localhost:8000/redoc`
- **健康检查**：`http://localhost:8000/health`

### 主要路由组

| 前缀 | 说明 |
|------|------|
| `/api/strategy` | 策略 CRUD / 生成 / 分析 |
| `/api/backtest` | 回测执行与结果 |
| `/api/collector` | 数据采集与管理 |
| `/api/realtime` | 实时行情 WebSocket |
| `/api/agent` | AI Agent 对话 |
| `/api/plugins` | 插件管理 |
| `/api/share` | 分享系统 |
| `/api/v2/models` | V2 模型管理 |
| `/api/v2/ensemble` | 集成模型 |
| `/api/v2/risk` | 风险指标 |
| `/api/v2/rl` | 强化学习接口 |
| `/ws/worker` | Worker WebSocket |

## 测试

```bash
# 单元测试
pytest backend/tests/unit/ -v

# 集成测试
pytest backend/tests/integration/ -v

# CLI 命令
quantcell tests main --unit
quantcell tests main --integration
```

测试覆盖率配置位于 `pyproject.toml`，目标 90%。

## 开发指南

### 新增策略

1. 在 `backend/strategy/templates/` 创建新文件
2. 继承基类并实现 `on_bar()` 等方法
3. 在前端策略编辑器中加载模板进行测试

### 新增后端 API

1. 在 `backend/<module>/routes.py` 中添加路由
2. 在 `backend/main.py` 中注册路由
3. 添加对应的 Service 层业务逻辑
4. 编写单元测试和集成测试

### 新增 CLI 子命令

1. 在 `backend/cli/<name>.py` 定义 `app = typer.Typer(...)`
2. 在 `backend/cli/__init__.py` 注册子命令
3. 在 `pyproject.toml` 的 `[project.scripts]` 无需修改

## 常见问题

### Q: 启动时提示端口被占用？
系统集成了 `PortManager`，默认自动分配可用端口。也可通过 `--port` 参数手动指定。

### Q: 如何配置交易所 API？
通过前端「设置 → 交易所」页面配置，或在 `config/binance_example.yaml` 中配置。API 密钥使用 `credentials` 模块加密存储。

### Q: 回测结果不准确？
检查：1) 数据完整性 (`quantcell data integrity`) 2) Walk-Forward 验证 3) 使用多数据源回测 (`data_sources=["kline", "deriv"]`)。

### Q: 如何开启调试模式？
```bash
# Web 服务
uvicorn main:app --debug

# CLI
LOG_LEVEL=DEBUG quantcell backtest run ...
```

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