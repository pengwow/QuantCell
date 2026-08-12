"""QuantCell 统一 CLI 入口。

定义顶层 typer app 和子命令注册函数。
子命令通过 register_commands() 懒加载, --help 时不触发不必要的模块初始化。
"""
from __future__ import annotations

import typer

app = typer.Typer(
    name="quantcell",
    help="QuantCell 统一 CLI — 策略 / 回测 / 数据 / 风控 / 工作进程 等",
    add_completion=False,
    no_args_is_help=True,
)

_registered: bool = False


def register_commands() -> None:
    """注册所有子命令(首次调用时才导入,避免 --help 触发 worker 初始化)。"""
    global _registered
    if _registered:
        return
    _registered = True

    from .agent import app as _agent_app
    from .backtest import app as _backtest_app
    from .data import app as _data_app
    from .market import app as _market_app
    from .migrate import app as _migrate_app
    from .news import app as _news_app
    from .plugin import app as _plugin_app
    from .rl import app as _rl_app
    from .strategy import app as _strategy_app
    from .tests_cmd import app as _tests_app
    from .web import app as _web_app
    from .worker import app as _worker_app
    from .account import app as _account_app

    app.add_typer(_agent_app,    name="agent",     help="AI agent 管理")
    app.add_typer(_backtest_app, name="backtest",  help="事件驱动回测(axon_quant 唯一)")
    app.add_typer(_data_app,     name="data",      help="数据采集 / 行情 / 存储")
    app.add_typer(_market_app,   name="market",    help="行情订阅 / 实时数据")
    app.add_typer(_migrate_app,  name="migrate",   help="数据库迁移")
    app.add_typer(_news_app,     name="news",      help="新闻 / 情绪数据")
    app.add_typer(_plugin_app,   name="plugin",    help="插件管理")
    app.add_typer(_rl_app,       name="rl",        help="强化学习训练 / 推理")
    app.add_typer(_strategy_app, name="strategy",  help="策略 CRUD / 生成 / 分析 / 优化 / 部署")
    app.add_typer(_tests_app,    name="tests",     help="跑测试套件")
    app.add_typer(_web_app,      name="web",       help="Web 服务管理和网页工具")
    app.add_typer(_worker_app,   name="worker",    help="Worker 工作进程管理")
    app.add_typer(_account_app,  name="account",   help="凭证管理（add/list/remove）")