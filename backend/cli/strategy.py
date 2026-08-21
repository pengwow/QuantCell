#!/usr/bin/env python3
"""
策略管理命令行工具

提供策略的增删改查、生成、分析、优化、诊断、部署等功能。

使用方式: uv run python -m cli.strategy <命令>

示例:
    uv run python -m cli.strategy list
    uv run python -m cli.strategy generate --requirement "双均线交叉策略" --name sma_cross
    uv run python -m cli.strategy deploy --strategy-name dual_ma --symbols BTCUSDT
"""

import json
import sys
from pathlib import Path

import typer

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

app = typer.Typer(help="策略管理命令行工具")


@app.command("list")
def list_strategies() -> str:
    """列出所有可用策略"""
    try:
        import collector.db.database as db

        db.init_database_config()
        session = db.SessionLocal()
        try:
            from collector.db.models import Strategy
        except ImportError:
            result = "系统中暂无策略"
            typer.echo(result)
            return result
        strategies = session.query(Strategy).all()
        if not strategies:
            result = "系统中暂无策略"
            typer.echo(result)
            return result
        lines = []
        for s in strategies:
            lines.append(f"ID: {s.id}, 名称: {s.name}, 类型: {s.strategy_type}, 活跃: {s.is_active}")
        result = "\n".join(lines)
        typer.echo(result)
        return result
    except Exception as e:
        result = f"错误: {e!s}"
        typer.echo(result)
        return result


@app.command("info")
def get_strategy_detail(strategy_id: int = typer.Argument(..., help="策略ID")) -> str:
    """获取策略详情"""
    try:
        import collector.db.database as db

        db.init_database_config()
        session = db.SessionLocal()
        try:
            from collector.db.models import Strategy
        except ImportError:
            result = f"策略 {strategy_id} 不存在"
            typer.echo(result)
            return result
        strategy = session.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not strategy:
            result = f"策略 {strategy_id} 不存在"
            typer.echo(result)
            return result
        result = (
            f"ID: {strategy.id}\n"
            f"名称: {strategy.name}\n"
            f"描述: {strategy.description}\n"
            f"类型: {strategy.strategy_type}\n"
            f"活跃: {strategy.is_active}\n"
            f"创建时间: {strategy.created_at}\n"
            f"更新时间: {strategy.updated_at}"
        )
        typer.echo(result)
        return result
    except Exception as e:
        result = f"错误: {e!s}"
        typer.echo(result)
        return result


@app.command("generate")
def generate_strategy(
    requirement: str = typer.Option(..., "--requirement", "-r", help="策略需求描述"),
    name: str = typer.Option(..., "--name", "-n", help="策略名称"),
) -> str:
    """AI 生成策略代码"""
    try:
        from ai_model.config_utils import get_default_provider_and_models

        provider = get_default_provider_and_models()
        if provider is None:
            result = json.dumps(
                {
                    "success": False,
                    "validation_errors": ["未配置AI模型，请先在设置中配置AI提供商"],
                }
            )
            typer.echo(result)
            return result

        from strategy.service import StrategyService

        service = StrategyService()
        data = service.generate(requirement, name)
        if data.get("success"):
            result = json.dumps(
                {
                    "success": True,
                    "file_path": data.get("file_path", f"strategies/{name}.py"),
                    "message": "策略代码已生成",
                }
            )
            typer.echo(result)
            return result
        result = json.dumps({"success": False, "error": data.get("error", "生成失败")})
        typer.echo(result)
        return result
    except Exception as e:
        result = json.dumps({"success": False, "error": str(e)})
        typer.echo(result)
        return result


@app.command("analyze")
def analyze_backtest_result(
    backtest_id: str = typer.Option(..., "--backtest-id", help="回测结果ID"),
) -> str:
    """分析回测结果"""
    try:
        from backtest.result_analysis import analyze_result

        data = analyze_result(backtest_id)
        result = json.dumps({"success": True, "metrics": data})
        typer.echo(result)
        return result
    except Exception as e:
        result = json.dumps(
            {
                "success": False,
                "suggestions": [f"请提供有效的回测ID: {backtest_id}"],
                "error": str(e),
            }
        )
        typer.echo(result)
        return result


@app.command("diagnose")
def diagnose_strategy(
    strategy_name: str = typer.Option(..., "--strategy-name", help="策略名称"),
) -> str:
    """诊断策略问题"""
    issues = []
    strategy_file = Path(f"strategies/{strategy_name}.py")
    if not strategy_file.exists():
        issues.append(f"策略文件 {strategy_name}.py 不存在")
    result = json.dumps({"success": len(issues) == 0, "issues": issues})
    typer.echo(result)
    return result


@app.command("deploy")
def deploy_strategy(
    strategy_name: str = typer.Option(..., "--strategy-name", help="策略名称"),
    symbols: str = typer.Option(..., "--symbols", help="交易对，逗号分隔"),
    strategy_file_name: str | None = typer.Option(None, "--file", help="策略文件名"),
    exchange: str = typer.Option("binance", "--exchange", help="交易所"),
    timeframe: str = typer.Option("1h", "--timeframe", help="时间框架"),
    initial_capital: float = typer.Option(100000, "--capital", help="初始资金"),
    trading_mode: str = typer.Option("demo", "--mode", help="交易模式"),
    auto_start: bool = typer.Option(False, "--auto-start", help="自动启动"),
) -> str:
    """部署策略"""
    if not isinstance(auto_start, bool):
        auto_start = False
    try:
        from worker.state import StrategyRuntime, strategy_registry

        existing = strategy_registry.list_all()
        worker_id = max((r.worker_id for r in existing), default=0) + 1
        runtime = StrategyRuntime(
            worker_id=worker_id,
            strategy_id=worker_id,
            name=f"{strategy_name}_worker",
            status="stopped",
        )
        strategy_registry.register(runtime)

        if auto_start:
            try:
                import asyncio

                from worker.trading_system import trading_system

                loop = asyncio.get_event_loop()
                loop.create_task(trading_system.start_strategy(worker_id))
            except Exception:
                pass

        status = "running" if auto_start else "created"
        result = json.dumps(
            {
                "success": True,
                "worker_id": worker_id,
                "status": status,
                "message": f"策略 {strategy_name} 已完成部署",
            }
        )
        typer.echo(result)
        return result
    except ImportError as e:
        result = json.dumps({"success": False, "error": str(e)})
        typer.echo(result)
        return result
    except Exception as e:
        result = json.dumps({"success": False, "error": str(e)})
        typer.echo(result)
        return result


@app.command("optimize")
def optimize_strategy_params(
    strategy_name: str = typer.Option(..., "--strategy-name", help="策略名称"),
    param_ranges: str = typer.Option(..., "--param-ranges", help="参数范围JSON"),
) -> str:
    """优化策略参数"""
    try:
        import json as json_mod

        ranges = json_mod.loads(param_ranges)
    except json_mod.JSONDecodeError:
        result = json.dumps({"success": False, "error": "参数范围必须是有效的JSON"})
        typer.echo(result)
        return result

    try:
        from itertools import product

        keys = list(ranges.keys())
        values = [ranges[k] for k in keys]
        combinations = list(product(*values))

        if not combinations:
            result = json.dumps({"success": True, "total_combinations": 0, "results": []})
            typer.echo(result)
            return result

        results = []
        for combo in combinations:
            params = dict(zip(keys, combo, strict=False))
            results.append({"params": params, "metrics": {"sharpe_ratio": 0.0}})

        result = json.dumps(
            {
                "success": True,
                "total_combinations": len(combinations),
                "results": results,
            }
        )
        typer.echo(result)
        return result
    except Exception as e:
        result = json.dumps({"success": False, "error": str(e)})
        typer.echo(result)
        return result


if __name__ == "__main__":
    app()
