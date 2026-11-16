---
title: CLI 命令行
description: quantcell 命令行完整参考 — 15 组子命令
---

# CLI 命令行

`uv sync` 后即在 Python 环境 bin 目录生成 `quantcell` 命令
（如 `backend/.venv/bin/quantcell`），任意目录可用。

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

每组子命令均支持 `--help` 查看完整参数，例如 `quantcell backtest run --help`。

## 常用任务速查

### 策略

```bash
quantcell strategy list                                    # 列出策略
quantcell strategy generate \
  --requirement "双均线金叉买入" --name my_strategy        # AI 生成
```

### 回测

```bash
quantcell backtest run -s dual_ma \
  --symbols BTCUSDT --timeframes 1h \
  --initial-capital 100000 --trading-mode spot
```

### 数据

```bash
quantcell data download -s BTCUSDT -i 1d                   # 下载行情
quantcell data quality check --start 20240101 --end 20241231
quantcell data import csv <文件路径>
quantcell market fetch --symbol BTCUSDT --interval 1h
```

### 强化学习

```bash
quantcell rl train -s BTCUSDT -a ppo -t 100000 -r sharpe
quantcell rl lifecycle -s BTCUSDT                          # 全生命周期
```

### Agent 与研究

```bash
quantcell agent ...            # Agent 管理与多轮对话
quantcell factor ...           # 因子分析 / 对比 / LLM 挖掘 / 快照
quantcell research ...         # 研究模块运维
quantcell news ...             # 新闻与市场情绪
quantcell web ...              # Web 搜索与抓取
```

### 运维

```bash
quantcell worker start <worker_id>        # 启动 Worker
quantcell worker list-workers             # 查看 Worker
quantcell account add|list|remove         # 凭证管理（加密存储）
quantcell migrate -y                      # 数据库迁移
quantcell tests main --unit               # 跑单元测试
quantcell plugin install x.zip            # 安装插件
```

## 测试运行脚本

`quantcell tests` 是对 pytest 的封装，定位与 CI 一致的子集：

```bash
quantcell tests main --unit        # 单元测试
quantcell tests main               # 全量
```

也可以直接使用 pytest：

```bash
cd backend && .venv/bin/python -m pytest tests/ -v
```
