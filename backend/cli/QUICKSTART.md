# QuantCell CLI 快速入门

`quantcell` 把原本散落在 `backend/scripts/` 的命令聚合为一个 typer 入口，当前注册
16 个子命令。历史上的 `scripts/*_cli.py` 薄 shim 已删除、兼容期结束，命令统一走
`quantcell`（或等价的 `python -m cli`）。

## 安装

```bash
cd backend && uv pip install -e .
```

`uv pip install -e .` 会把 `quantcell` 命令注册到当前 venv。

## 查看顶层帮助

```bash
quantcell --help
```

输出（rich 表格边框从略）：

```
 Usage: quantcell [OPTIONS] COMMAND [ARGS]...

 QuantCell 命令行工具

 Commands:
   agent     Agent 管理命令行工具
   factor    因子研究（分析/对比/代码因子/合成因子/LLM 挖掘/快照）
   market    市场数据命令行工具
   news      新闻与市场情绪工具
   plugin    插件管理命令行工具
   research  研究模块运维命令
   rl        RL 命令行工具
   web       Web 搜索与抓取工具
   worker    Worker 管理命令行工具
   tests     QuantCell 测试运行脚本
   account   凭证管理（add/list/remove）
   migrate   数据库迁移(SQLite schema 升级)
   strategy  策略管理命令行工具
   backtest  QuantCell 回测工具（事件驱动引擎 axon-quant）
   jobs      作业池观测与自检
   data      数据管理命令行工具
```

## 常用命令速查

| 任务 | 命令 |
|------|------|
| 列出策略 | `quantcell strategy list` |
| 启动回测 | `quantcell backtest run --strategy sma_crossover --symbols BTCUSDT --timeframes 1h` |
| 训练 RL | `quantcell rl train --symbol BTCUSDT` |
| 启动 Worker | `quantcell worker start <id>` |
| 安装插件 | `quantcell plugin install --zip plugin.zip` |
| 跑测试 | `quantcell tests main --unit` |
| 迁移数据库 | `quantcell migrate -y`（等价 `quantcell migrate run -y`） |
| 拉行情 | `quantcell market klines --symbol BTCUSDT --timeframe 1h` |
| 拉新闻 | `quantcell news news bitcoin -n 5` |
| 下载归档数据 | `quantcell data archive download -k aggTrades -m spot -s BTCUSDT --start 2024-01-01 --end 2024-01-02` |
| 搜网页 | `quantcell web search "bitcoin"` |
| 列出 Agent 工具 | `quantcell agent tool list` |
| 分析因子 | `quantcell factor analyze momentum_20d -s BTCUSDT -s ETHUSDT` |
| 对比因子 | `quantcell factor compare momentum_10d momentum_60d -s BTCUSDT` |
| LLM 挖掘 | `quantcell factor mine -s BTCUSDT -s ETHUSDT --candidates 4 --rounds 2 -o mine.json` |
| 代码因子入库 | `quantcell factor code add -n my_alpha -f alpha.py` |

## 命令行为要点

- **失败即非 0 退出**：`news news` / `news sentiment` / `web search` / `web fetch`
  在缺 API key、网络异常、非法 URL 等情况下把错误写到 stderr 并 exit 1，不再打
  一行错误后返回 0；成功时的输出格式与以前一致。
- **migrate 三种写法等价**：`quantcell migrate -y`、`quantcell migrate run -y`、
  `python -m cli.migrate -y` 都会直接执行迁移；漏掉 `-y` 时先确认。
- **tests 按路径直达**：`--unit` / `--integration` / `--api` / `--auth` / `--schema`
  / `--error` 分别落到 `tests/unit`、`tests/integration`、`tests/integration/api`、
  `tests/integration/api/test_auth.py` 等具体文件或目录，不再用 pytest 的 `-m`
  标记筛选（那些目录里几乎没有对应 mark，筛出来是 0 个用例）。也可以直接传路径：
  `quantcell tests main tests/unit/cli`。
- **data download 已废弃**：`quantcell data download` 只打印错误并 exit 1，指向
  `quantcell data archive download`。后者必须给 `-k/--kind`（aggTrades、trades、
  bookDepth、bookTicker、markPriceKlines、indexPriceKlines、premiumIndexKlines）、
  `-m/--market`（spot / um / cm）、`-s/--symbols`（逗号分隔）、`--start`、`--end`，
  `-i/--interval` 按需给。
- **strategy 走真实服务**：`strategy list` 直查策略库（空库输出「系统中暂无策略」）；
  `strategy generate` 调用 `strategy.service.generate_strategy` 并把代码落盘为
  `backend/strategies/<name>.py`（需要先配置可用 AI 模型）；`strategy deploy --auto-start`
  不受 CLI 支持 —— 只注册 runtime 并在 stderr 提示改用 `quantcell worker start`
  或 Web 页面启动。

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

因子定义（内置 / 表达式 / 代码 / 合成）统一存在 SQLite 的 `factor_catalog` 表，与 Web 端
是同一份数据，没有按因子类型拆分的独立存储开关。需要隔离环境时改数据目录
（`QUANTCELL_DATA_DIR`）或库文件（`DB_FILE`）。

## 两个等价入口

```bash
# 1. 安装后直接用 quantcell(推荐)
quantcell strategy list

# 2. 不安装,直接用模块方式调入口
python -m cli strategy list
```

`python -m cli.<子模块>`（如 `python -m cli.migrate -y`）也可单独跑某个子命令，用于调试。

## agent 子命令分组

`quantcell agent` 分 6 组，目前只有 `tool` / `params` 是真实实现：

```bash
quantcell agent tool list             # 列出后端注册表里的工具
quantcell agent tool info <tool>      # 工具描述与参数 schema
quantcell agent params tools          # 有可配置参数的工具清单
quantcell agent params show <tool>    # 查看某工具的参数
quantcell agent params set <tool> <param> <value>
```

`session` / `chat` / `workspace` / `action` 四组是显式未实现：执行即 exit 1 并在
stderr 提示改用 Web `/agent` 页（会话持久层、AgentLoop、工作区读写都还没接到 CLI），
不会静默返回或打印假成功。

```bash
quantcell agent session list          # exit 1:提示用 Web /agent 页
quantcell agent chat history <sid>    # exit 1:同上
quantcell agent workspace cat README  # exit 1:同上
quantcell agent action generate-strategy -r "双均线" -n my_strat   # exit 1:同上
```

## 迁移现状

- **已完成**: 命令全部平迁到 `cli/<name>.py` 并注册进主 app；`backend/scripts/` 下的
  `*_cli.py`、`run_tests.py`、`migrate_db.py` 等兼容 shim 已删除（见提交 `23fd06ad`），
  兼容期结束。
- **scripts 目录只剩工具脚本**: `bench_backtest_baseline.py`、
  `export_leverage_brackets.py`、`export_vocab_types.py`、`seed_backtest_demo.py`、
  `vocab_lint.py` —— 它们是按原用途直接运行的工具，不提供 `quantcell` 子命令。
- **回滚**: shim 已从工作区移除，`.trash/scripts_shim_backups/` 备份目录也已清理；
  确需旧文件用 `git checkout <commit> -- backend/scripts/` 从历史取回。

## 开发扩展

新增子命令:

1. 在 `cli/<name>.py` 定义 `app = typer.Typer(...)` 和命令
2. 在 `cli/__init__.py` 加 `app.add_typer(<name>_app, name="<name>", help="...")`
3. 在 `pyproject.toml` 的 `[project.scripts]` 已经有 `quantcell = "cli.__main__:main"`,无需改
4. 共享辅助从 `cli._common` 拿:`get_logger()`,`echo_json()`,`handle_errors`,`backend_path_option()`

不要在每个子命令里重复定义 logger / 异常处理 / JSON 输出格式。
