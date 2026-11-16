# QuantCell — AI 原生量化交易系统

[English](README.md) | 简体中文

[Demo 地址](https://demo.quantcell.top/chart) | [项目主页](https://quantcell.top)

## 1. 项目简介

QuantCell 是一款 AI 原生的量化交易系统，以 `axon-quant`（Rust 核心）为交易引擎，以 FastAPI 为服务框架、React + TypeScript 为前端，提供从策略开发、回测验证到实盘部署的全流程能力。

核心设计理念：**让量化交易变得简单、高效、智能**——自然语言即可描述策略，AI 自动生成代码并完成回测验证。

系统采用**统一内核架构**：回测、模拟盘（paper）与实盘（live）共用同一条由 axon-quant 内核驱动的 per-bar 主回路，模式差异只在数据泵与执行层装配，保证回测与实盘行为一致。

## 2. 桌面客户端

支持 macOS / Windows / Linux 桌面端。桌面版基于 Tauri 2 壳复用同一套 `frontend/` 代码，通过 PyInstaller 打包本地 `backend`（FastAPI + axon-quant）作为 sidecar 进程随桌面端自动拉起；`local` 模式免登录直达，也支持 `remote` 模式连接远端服务。

| 平台 | 架构 | 安装包 |
|------|------|--------|
| macOS（Apple 芯片 M 系列） | aarch64 | `QuantCell_<ver>_aarch64.dmg` |
| macOS（Intel） | x86_64 | `QuantCell_<ver>_x64.dmg` |
| Windows | x86_64 | `QuantCell_<ver>_x64.msi` / `.exe` |
| Linux | x86_64 | `quantcell_<ver>_amd64.deb` / `.AppImage` |

- 下载位置：GitHub Actions **artifacts**（`quantcell-desktop-*`），tag `v*` 触发时自动生成
- 未签名：macOS 首次打开需右键 → 打开；Windows 提示未知发布者，点击「仍要运行」
- CI 打包 workflow：`.github/workflows/desktop-build.yml`，手动 `workflow_dispatch` 或打 `v*` tag 触发

> 详细桌面端开发与打包说明见 [desktop/README.md](desktop/README.md)。

## 3. 核心特性

### 🤖 AI 智能

- **自然语言策略生成**：中文描述交易想法，AI 自动生成可执行策略代码
- **思维链推理**：多步骤策略生成与指标生成，逻辑可解释、可追溯
- **代码质量自检**：自动校验语法与运行时安全，拒绝不安全代码
- **智能 Agent**：具备记忆与工具调用能力的 AI Agent，可进行多轮对话与操作编排
- **LLM 决策录制回放**：LLM 策略回测时从录制记录回放决策，不真实请求 LLM

### ⚡ Axon-Quant 高性能引擎

- **Rust 核心驱动**：底层采用 `axon-quant 0.25.0`，统一内核架构
- **统一主回路**：回测 / paper / live 共用同一条 per-bar 编排，语义一致
- **多数据类型回测**：K 线、衍生数据（资金费率等）、订单簿、逐笔成交等数据适配器
- **Walk-Forward 验证**：滚动窗口回测，防止过拟合
- **HPO 超参优化**：内置 optuna 超参数优化

### 🎯 强化学习

- **Gymnasium 量化环境**：内置交易 Gym 环境
- **Stable-Baselines3**：支持 PPO / SAC / DQN 等主流算法
- **完整生命周期**：训练 → 回测 → 评估 → 重训练，支持 Walk-Forward 验证

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

- **React 19 + TypeScript + Vite 8**：类型安全的组件化开发
- **Ant Design 6**：企业级 UI 组件库
- **KLineCharts / ECharts**：专业级 K 线与指标图表
- **Zustand**：轻量高效的全局状态
- **i18n 国际化**：中英文无缝切换（i18next）
- **Monaco 编辑器**：内置代码编辑器

## 4. 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                    前端 (React + TypeScript)               │
│      Ant Design 6 · KLineCharts · Zustand · i18n · Tauri  │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼───────────────────────────────┐
│                 API Layer (FastAPI, /api/v1)              │
│   CORS · 认证 · 异常处理 · 能力开关 · Prometheus 可观测      │
└──────┬───────────────┬────────────────┬───────────────────┘
       │               │                │
       ▼               ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ 策略与回测    │  │ 实时交易     │  │ 数据采集     │
│ strategy/   │  │ realtime/   │  │ collector/  │
│ backtest/   │  │ worker/     │  │ quality/    │
│ factor/rl   │  │ credentials │  │ marketdata/ │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────────────────────────────────────────────────┐
│       axon-quant (Rust 内核) · Binance / OKX · DuckDB     │
│        回测 / paper / live 共用统一 per-bar 主回路          │
└──────────────────────────────────────────────────────────┘
       ▲                ▲                ▲
┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
│   Agent     │  │   CLI       │  │   插件      │
│  agent/     │  │  quantcell  │  │  plugins/   │
│  research/  │  │  15 组命令   │  │  事件总线    │
└─────────────┘  └─────────────┘  └─────────────┘
```

## 5. 技术栈

| 类别 | 技术 |
|------|------|
| 后端语言 | Python 3.14 |
| Web 框架 | FastAPI 0.136（uvicorn） |
| 交易引擎 | axon-quant 0.25.0（Rust 核心，path 依赖） |
| 数据库 | DuckDB 1.4 + Parquet + SQLAlchemy 2 + Alembic |
| 数据处理 | Pandas 2.3 / PyArrow 22 |
| 强化学习 | Gymnasium 1.3 + Stable-Baselines3 2.9 |
| 命令行 | Typer 0.20 |
| 前端框架 | React 19 + TypeScript 5.9 + Vite 8 |
| UI 组件 | Ant Design 6 + TailwindCSS 4 |
| 图表 | KLineCharts 10 + ECharts 5.5 |
| 状态管理 | Zustand 5 |
| 国际化 | i18next / react-i18next |
| 桌面端 | Tauri 2 + PyInstaller（backend sidecar） |
| 包管理 | uv（后端）/ bun（前端） |
| 代码规范 | ruff（lint + format） |
| 测试 | pytest 9 + coverage（覆盖率基线 57%） |

## 6. 快速开始

### 环境要求

| 组件 | 版本 |
|------|------|
| Python | 3.14 |
| uv | latest |
| bun | latest |

> 桌面端开发另需 Rust 工具链（Tauri 2），见 [desktop/README.md](desktop/README.md)。

### 一键安装与启动

```bash
git clone https://github.com/pengwow/quantcell.git
cd quantcell
bash scripts/install.sh --minimal   # 自动安装 uv/bun 工具链、前后端依赖并启动
```

`scripts/install.sh` 支持 `--minimal`（最小化依赖）/ `--full`（完整依赖）/ `--extra <pkg>`（可选依赖组）三种模式。

也可通过 Makefile 管理 dev 服务：

```bash
make dev-start      # 启动前后端开发服务
make dev-status     # 查看运行状态
make dev-stop       # 停止服务
```

### 手动安装

**后端**

```bash
cd backend
uv sync                        # 安装依赖并生成 quantcell CLI 入口
uv run python init_db.py       # 初始化数据库
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

## 7. CLI 使用

安装后（`uv sync`）即生成 `quantcell` 命令，共 15 组子命令：

```
$ quantcell --help
 Usage: quantcell [OPTIONS] COMMAND [ARGS]...

 QuantCell 命令行工具

 Commands:
   agent       Agent 管理命令行工具
   factor      因子研究（分析/对比/代码因子/合成因子/LLM 挖掘/快照）
   market      市场数据命令行工具
   news        新闻与市场情绪工具
   plugin      插件管理命令行工具
   research    研究模块运维命令
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

> `quantcell` 可执行文件位于 Python 环境 bin 目录（如 `backend/.venv/bin/quantcell`），`uv sync` 后可直接在任意目录使用。

### 命令速查

| 任务 | 命令 |
|------|------|
| 列出策略 | `quantcell strategy list` |
| AI 生成策略 | `quantcell strategy generate --requirement "双均线金叉买入" --name my_strategy` |
| 运行回测 | `quantcell backtest run -s dual_ma --symbols BTCUSDT --timeframes 1h` |
| 下载行情数据 | `quantcell data download -s BTCUSDT -i 1d` |
| 数据质量检查 | `quantcell data quality check --start 20240101 --end 20241231` |
| 从 CSV 导入数据 | `quantcell data import csv <文件路径>` |
| 查看市场行情 | `quantcell market fetch --symbol BTCUSDT --interval 1h` |
| 训练 RL 模型 | `quantcell rl train -s BTCUSDT -a ppo -t 100000 -r sharpe` |
| RL 全生命周期 | `quantcell rl lifecycle -s BTCUSDT` |
| 启动 Worker | `quantcell worker start <worker_id>` |
| 查看 Worker | `quantcell worker list-workers` |
| 查看账户 | `quantcell account list` |
| 迁移数据库 | `quantcell migrate -y` |
| 跑单元测试 | `quantcell tests main --unit` |
| 安装插件 | `quantcell plugin install x.zip` |

## 8. 核心功能使用

### 1. AI 生成策略

在前端对话界面输入，或在命令行直接生成：

```bash
quantcell strategy generate \
  --requirement "基于双均线的趋势跟踪策略，快线 10 天、慢线 30 天，金叉买入、死叉卖出" \
  --name dual_ma
```

系统自动完成：理解需求 → 生成代码 → 安全校验 → 回测验证 → 输出报告。

### 2. 运行回测

CLI 方式（`-s` 为策略名，可用 `quantcell strategy list` 查看可用策略）：

```bash
quantcell backtest run \
  -s dual_ma \
  --symbols BTCUSDT \
  --timeframes 1h \
  --initial-capital 100000 \
  --trading-mode spot
```

Python 方式（详细用法见 [backend/backtest/README.md](backend/backtest/README.md)）：

```python
from backtest.engine_service import EventDrivenBacktestService
from backtest.data_provider import BacktestDataProvider

provider = BacktestDataProvider()               # 数据提供者（Parquet/CSV）
service = EventDrivenBacktestService(provider)
result = service.run_backtest(
    strategy_name="dual_ma",
    strategy_params={"fast": 10, "slow": 30},
    symbols=["BTCUSDT"],
    timeframes=["1h"],
    engine_config={"initial_capital": 100_000},
    data_type="kline",
    market="spot",
)
print(result)  # 返回含收益率/最大回撤/成交记录等指标的 dict
```

回测默认走 axon-quant 统一内核（`worker.Kernel`），三条执行路径（统一内核 / legacy 引擎 / Python 回退）由 `engine_config['runner']` 选择，输出统一 `BacktestResult` 契约。

### 3. 强化学习训练

```bash
quantcell rl train \
    -s BTCUSDT \
    -a ppo \
    -t 100000 \
    -r sharpe

# 一键生命周期: 训练 → 回测 → 评估 → 重训练
quantcell rl lifecycle -s BTCUSDT --train-steps 30000 --retrain-steps 10000
```
