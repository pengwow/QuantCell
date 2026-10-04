# QuantCell CLI 快速入门

`quantcell` 统一了原本分散在 `backend/scripts/` 下 12 个独立命令,
通过 typer 聚合为一个命令,12 个子命令,保持 6 个月兼容期 shim。

## 安装

```bash
cd backend && uv pip install -e .
```

`uv pip install -e .` 会把 `quantcell` 命令注册到当前 venv。

## 查看顶层帮助

```bash
quantcell --help
```

输出:

```
 Usage: quantcell [OPTIONS] COMMAND [ARGS]...
 QuantCell 统一 CLI — 策略 / 回测 / 数据 / 风控 / 工作进程 等
 Commands:
   agent     AI agent 管理
   backtest  事件驱动回测(axon_quant 唯一)
   data      数据采集 / 行情 / 存储
   factor    因子研究（分析/对比/代码因子/合成因子/LLM 挖掘/快照）
   market    行情订阅 / 实时数据
   migrate   数据库迁移
   news      新闻 / 情绪数据
   plugin    插件管理
   rl        强化学习训练 / 推理
   strategy  策略 CRUD / 生成 / 分析 / 优化 / 部署
   tests     跑测试套件
   web       启动 / 停止 Web 服务
   worker    Worker 工作进程管理
```

## 常用命令速查

| 任务 | 新命令 (推荐) | 旧 shim (6 个月内可用) |
|------|--------------|---------------------|
| 列出策略 | `quantcell strategy list` | `python scripts/strategy_cli.py list` |
| 启动回测 | `quantcell backtest run ...` | `python scripts/backtest_cli.py run ...` |
| 训练 RL | `quantcell rl train --symbol BTCUSDT` | `python scripts/rl_cli.py train --symbol BTCUSDT` |
| 启动 Worker | `quantcell worker start <id>` | `python scripts/worker_cli.py start <id>` |
| 安装插件 | `quantcell plugin install --zip x.zip` | `python scripts/plugin_cli.py install --zip x.zip` |
| 跑测试 | `quantcell tests main --unit` | `python scripts/run_tests.py --unit` |
| 迁移数据库 | `quantcell migrate run -y` | `python scripts/migrate_db.py` |
| 拉行情 | `quantcell market klines --symbol BTCUSDT` | `python scripts/market_cli.py klines --symbol BTCUSDT` |
| 拉新闻 | `quantcell news news --query bitcoin` | `python scripts/news_cli.py news --query bitcoin` |
| 下载数据 | `quantcell data download -s BTCUSDT -i 1d` | `python scripts/data_cli.py download -s BTCUSDT -i 1d` |
| 搜网页 | `quantcell web search "bitcoin"` | `python scripts/web_cli.py search "bitcoin"` |
| 聊 Agent | `quantcell agent chat send "hi"` | `python scripts/agent_cli.py chat send "hi"` |
| 分析因子 | `quantcell factor analyze momentum_20d -s BTCUSDT -s ETHUSDT` | — |
| 对比因子 | `quantcell factor compare momentum_10d momentum_60d -s BTCUSDT` | — |
| LLM 挖掘 | `quantcell factor mine -s BTCUSDT -s ETHUSDT --candidates 4 --rounds 2 -o mine.json` | — |
| 代码因子入库 | `quantcell factor code add my_alpha -f alpha.py` | — |

## factor 子命令

与 Web 端因子分析同口径（进程内直调 FactorService，不走 HTTP）。默认 rich 文本输出，
`--json` 输出完整结构化结果，`-o/--output` 将 JSON 落文件（挖掘结果可直接喂给合成因子）。

```bash
# 浏览
quantcell factor list [--kind builtin|expression|code|composite] [--json]
quantcell factor get momentum_20d
quantcell factor instruments --candle-type spot

# 分析与对比（参数与页面一致：周期/分组/滚动窗/前瞻/衰减滞后/单边成本）
quantcell factor analyze momentum_20d -s BTCUSDT -s ETHUSDT -i 1h \
    --method spearman --groups 5 --window 20 --forward 1 --horizons 1,2,3,5,10 --cost-bps 10
quantcell factor compare momentum_10d momentum_60d -s BTCUSDT -s ETHUSDT --json -o cmp.json

# 表达式因子
quantcell factor expression validate -e "close / open - 1"
quantcell factor expression add -n my_expr -e "close / open - 1"
quantcell factor expression delete my_expr

# 代码因子（沙箱校验：AST 白名单 + 子进程资源限制）
quantcell factor code validate -f alpha.py        # 或 --code 'factor = ...'
quantcell factor code add -n my_alpha -f alpha.py -d "说明"
quantcell factor code delete my_alpha

# 合成因子：spec JSON 取自 mine 结果的 composite 块（constituents/train_window）
quantcell factor composite add -n my_comp --spec composite_spec.json
quantcell factor composite delete my_comp

# LLM 挖掘（使用系统配置的默认 AI 模型；进度走 stderr，不污染 stdout JSON）
quantcell factor mine -s BTCUSDT -s ETHUSDT \
    --candidates 3 --rounds 2 --top-k 5 --temperature 0.8 \
    --test-ratio 0.3 --wf-folds 3 --dedup-corr 0.9 --compose \
    -o mine.json
# --no-compose 关闭合成；--wf-folds 0 用单次样本外切分；--dedup-corr 0 关闭相关性去重

# 快照与档案
quantcell factor snapshot save -f momentum_20d -s BTCUSDT
quantcell factor snapshot list momentum_20d --limit 20
quantcell factor snapshot delete 12
quantcell factor catalog
```

自定义因子存储路径可用环境变量覆盖（便于隔离环境）：
`QC_FACTOR_EXPR_STORE` / `QC_FACTOR_CODE_STORE` / `QC_FACTOR_COMPOSITE_STORE`。

## 三个等价入口

CLI 支持 3 种调用方式,完全等价:

```bash
# 1. 安装后直接用 quantcell(推荐)
quantcell strategy list

# 2. 不安装,直接调 cli.run
python -m cli.run strategy list

# 3. 6 个月内继续用旧 scripts
python scripts/strategy_cli.py list
```

## 子命令分组

`quantcell agent` 还支持二级子命令:

```bash
quantcell agent session list          # 列出所有会话
quantcell agent chat send "Hello"     # 发送消息
quantcell agent tool list             # 列出所有工具
quantcell agent workspace cat README  # 查看工作空间文件
quantcell agent action generate-strategy -r "双均线" -n my_strat
```

## 迁移策略

- **本次(已完成)**: 12 个 scripts 平迁到 `cli/<name>.py`,原 scripts 改为薄 shim,转调 `cli.<name>.app`
- **6 个月后**: 删除整个 `backend/scripts/` 目录(除 `__pycache__` 等),`quantcell` 命令继续工作
- **回滚方案**: shim 文件备份在 `backend/.trash/scripts_shim_backups/`,如需回滚直接 `mv` 回来

## 开发扩展

新增子命令:

1. 在 `cli/<name>.py` 定义 `app = typer.Typer(...)` 和命令
2. 在 `cli/__init__.py` 加 `app.add_typer(<name>_app, name="<name>", help="...")`
3. 在 `pyproject.toml` 的 `[project.scripts]` 已经有 `quantcell = "cli.run:cli"`,无需改
4. 共享辅助从 `cli._common` 拿:`get_logger()`,`echo_json()`,`handle_errors`,`backend_path_option()`

不要在每个子命令里重复定义 logger / 异常处理 / JSON 输出格式。
