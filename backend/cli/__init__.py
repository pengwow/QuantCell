"""QuantCell 统一 CLI 入口 — 聚合所有子命令。

`quantcell` 一个命令,12 个子命令,统一替代 12 个分散的 scripts/ 脚本。

迁移策略:
- 业务逻辑从 scripts/ 平迁到 cli/<name>.py
- 原 scripts/<name>.py 改为 thin shim,转调 cli.<name>.app
- 6 个月兼容期后,删除整个 scripts/ 目录

设计原则:
- 不修改原 scripts/ 的业务逻辑,只搬位置
- cli 包只做 typer 聚合,共享辅助从 _common / _output 来
- 入口点 cli.run:cli,被 pyproject.toml 注册为 ``quantcell`` 命令
"""
from __future__ import annotations

import typer

from .agent import app as agent_app
from .backtest import app as backtest_app
from .data import app as data_app
from .market import app as market_app
from .migrate import app as migrate_app
from .news import app as news_app
from .plugin import app as plugin_app
from .rl import app as rl_app
from .strategy import app as strategy_app
from .tests_cmd import app as tests_app
from .web import app as web_app
from .worker import app as worker_app
from .account import app as account_app

# 顶层 typer app
app = typer.Typer(
    name="quantcell",
    help="QuantCell 统一 CLI — 策略 / 回测 / 数据 / 风控 / 工作进程 等",
    add_completion=False,
    no_args_is_help=True,
)

# 注册 12 个子命令
app.add_typer(agent_app, name="agent", help="AI agent 管理")
app.add_typer(backtest_app, name="backtest", help="事件驱动回测(axon_quant 唯一)")
app.add_typer(data_app, name="data", help="数据采集 / 行情 / 存储")
app.add_typer(market_app, name="market", help="行情订阅 / 实时数据")
app.add_typer(migrate_app, name="migrate", help="数据库迁移")
app.add_typer(news_app, name="news", help="新闻 / 情绪数据")
app.add_typer(plugin_app, name="plugin", help="插件管理")
app.add_typer(rl_app, name="rl", help="强化学习训练 / 推理")
app.add_typer(strategy_app, name="strategy", help="策略 CRUD / 生成 / 分析 / 优化 / 部署")
app.add_typer(tests_app, name="tests", help="跑测试套件")
app.add_typer(web_app, name="web", help="Web 服务管理和网页工具")
app.add_typer(worker_app, name="worker", help="Worker 工作进程管理")
app.add_typer(account_app, name="account", help="凭证管理（add/list/remove）")
