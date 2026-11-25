# QuantCell 后端快速上手

> 30 分钟跑通第一个事件驱动回测

## 前置

- Python 3.14
- Rust 编译环境（交易内核是 maturin path 依赖，首次 `uv sync` 会现编）

## 安装

```bash
cd backend
uv sync
.venv/bin/quantcell --help   # 应输出 15 个子命令
```

## 跑回测

```bash
# 事件驱动回测
.venv/bin/quantcell backtest run --strategy dualma --symbols BTCUSDT --timeframes 1h
```

回测默认走统一内核（回测 / paper / live 共用同一条 per-bar 主回路），
三条执行路径（`kernel` / `legacy` / `python`）见
[docs/zh/user-guide/backtesting.md](../../docs/zh/user-guide/backtesting.md)。

## 统一 CLI 入口

`quantcell` 命令聚合 15 个子命令：

| 子命令 | 用途 |
|---|---|
| `agent` | AI agent 管理 |
| `factor` | 因子挖掘 / 管理 |
| `market` | 行情订阅 / 实时数据 |
| `news` | 新闻 / 情绪数据 |
| `plugin` | 插件管理 |
| `research` | 研究工作流 |
| `rl` | 强化学习训练 / 推理 |
| `web` | 启动 / 停止 Web 服务 |
| `worker` | Worker 工作进程管理 |
| `tests` | 跑测试套件 |
| `account` | 凭证管理（add/list/remove） |
| `migrate` | 数据库迁移（SQLite schema 升级） |
| `strategy` | 策略 CRUD / 生成 / 分析 / 优化 / 部署 |
| `backtest` | 事件驱动回测 |
| `data` | 数据采集 / 行情 / 存储 |

旧 `scripts/*_cli.py` 各入口转发到 `cli.*` 模块。

## 架构

三层：前端（React）→ 业务层（`services/` `strategy/` `backtest/` …）→ Rust 交易内核。
引擎调用统一经 `backtest/engine_service.py`（回测）与 `worker/strategy_manager.py`
（paper / live），业务代码不直连引擎内部 API。详见
[docs/zh/user-guide/architecture.md](../../docs/zh/user-guide/architecture.md)。

## 跑测试

```bash
cd backend
.venv/bin/python -m pytest tests/unit -q       # 单元测试
.venv/bin/python -m pytest tests/conformance -q  # 契约门禁
```