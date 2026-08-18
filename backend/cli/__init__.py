#!/usr/bin/env python3
"""
QuantCell 命令行工具统一入口

使用方式: uv run python -m cli <子命令>
注册为 ``quantcell`` 命令。
"""

import sys
from pathlib import Path

import typer

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

app = typer.Typer(
    name="quantcell",
    help="QuantCell 命令行工具",
    add_completion=False,
    invoke_without_command=True,
)


def register_commands() -> None:
    """注册所有子命令到主 app。"""
    from cli.account import app as account_app
    from cli.agent import app as agent_app
    from cli.market import app as market_app
    from cli.migrate import app as migrate_app
    from cli.news import app as news_app
    from cli.plugin import app as plugin_app
    from cli.rl import app as rl_app
    from cli.tests_cmd import app as tests_app
    from cli.web import app as web_app
    from cli.worker import app as worker_app

    app.add_typer(agent_app, name="agent")
    app.add_typer(market_app, name="market")
    app.add_typer(news_app, name="news")
    app.add_typer(plugin_app, name="plugin")
    app.add_typer(rl_app, name="rl")
    app.add_typer(web_app, name="web")
    app.add_typer(worker_app, name="worker")
    app.add_typer(tests_app, name="tests")
    app.add_typer(account_app, name="account")
    app.add_typer(migrate_app, name="migrate")

    # strategy: 先注册, 完整实现已迁移到 cli/strategy.py
    from cli.strategy import app as strategy_app

    app.add_typer(strategy_app, name="strategy")

    # backtest: 转发到 backtest.cli
    from backtest.cli import app as backtest_app

    app.add_typer(backtest_app, name="backtest")

    # data: 直接转发到 cli.data (内部有真实实现)
    from cli.data import app as data_app

    app.add_typer(data_app, name="data")
