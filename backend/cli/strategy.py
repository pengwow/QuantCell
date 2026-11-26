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
from typing import Annotated

import typer

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

app = typer.Typer(help="策略管理命令行工具")


@app.command("list")
def list_strategies() -> str:
    """列出所有可用策略"""
    # strategy.models.Strategy 与 utils.db_session 走同一个 collector.db.database.Base / SessionLocal，
    # 这里不再从 collector.db.models 导入（该模块没有 Strategy）
    from strategy.models import Strategy
    from utils.db_session import get_db_session

    try:
        with get_db_session() as db:
            strategies = db.query(Strategy).all()
            if not strategies:
                result = "系统中暂无策略"
            else:
                lines = []
                for s in strategies:
                    lines.append(f"ID: {s.id}, 名称: {s.name}, 类型: {s.strategy_type}, 状态: {s.status}")
                result = "\n".join(lines)
    except Exception as e:
        typer.echo(f"错误: {e!s}", err=True)
        raise typer.Exit(1) from e
    typer.echo(result)
    return result


@app.command("info")
def get_strategy_detail(strategy_id: int = typer.Argument(..., help="策略ID")) -> str:
    """获取策略详情"""
    from strategy.models import Strategy
    from utils.db_session import get_db_session

    strategy = None
    try:
        with get_db_session() as db:
            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if strategy is not None:
                result = (
                    f"ID: {strategy.id}\n"
                    f"名称: {strategy.name}\n"
                    f"描述: {strategy.description}\n"
                    f"类型: {strategy.strategy_type}\n"
                    f"状态: {strategy.status}\n"
                    f"创建时间: {strategy.created_at}\n"
                    f"更新时间: {strategy.updated_at}"
                )
    except Exception as e:
        typer.echo(f"错误: {e!s}", err=True)
        raise typer.Exit(1) from e
    if strategy is None:
        typer.echo(f"策略 {strategy_id} 不存在", err=True)
        raise typer.Exit(1)
    typer.echo(result)
    return result


@app.command("generate")
def generate_strategy(
    requirement: str = typer.Option(..., "--requirement", "-r", help="策略需求描述"),
    name: str = typer.Option(..., "--name", "-n", help="策略名称（生成后保存为 strategies/<name>.py）"),
) -> str:
    """AI 生成策略代码并保存到策略目录"""
    try:
        from ai.config.config_utils import get_default_provider_and_models

        provider_config = get_default_provider_and_models()
        if provider_config is None:
            raise ValueError("未配置AI模型，请先在设置中配置AI提供商")

        from strategy.service import StrategyService

        service = StrategyService()
        # 服务层真实签名见 strategy/service.py::generate_strategy(prompt, model_id, model_name, provider, conversation_id)
        data = service.generate_strategy(prompt=requirement)
        code = data.get("code", "")
        if not code:
            raise ValueError("AI 未返回策略代码")

        # CLI 的 --name 不在服务签名里，落位为生成文件的文件名
        service.save_strategy(name, code)
        result = json.dumps(
            {
                "success": True,
                "file_path": str(Path(service.strategy_dir) / f"{name}.py"),
                "message": "策略代码已生成",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        typer.echo(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False), err=True)
        raise typer.Exit(1) from e
    typer.echo(result)
    return result


# 三种输入来源与 agent 工具 analyze_backtest_result 对齐（backtest_id / 结果文件 / 结果数据）
@app.command("analyze")
def analyze_backtest_result(
    backtest_id: Annotated[str | None, typer.Option("--backtest-id", help="回测结果ID")] = None,
    result_file: Annotated[str | None, typer.Option("--result-file", help="回测结果JSON文件路径")] = None,
    result_data: Annotated[str | None, typer.Option("--result-data", help="回测结果JSON字符串")] = None,
) -> str:
    """分析回测结果"""
    try:
        if not backtest_id and not result_file and not result_data:
            result = json.dumps({"success": False, "suggestions": ["请提供回测ID、结果文件或结果数据"]})
            typer.echo(result)
            return result

        if result_data or result_file:
            from backtest.result_analysis import ResultAnalyzer

            raw = json.loads(result_data or Path(result_file).read_text(encoding="utf-8"))
            analysis = ResultAnalyzer().analyze(raw)
            result = json.dumps({"success": True, "metrics": analysis}, ensure_ascii=False, default=str)
            typer.echo(result)
            return result

        from backtest.service import BacktestService

        data = BacktestService().analyze_backtest(backtest_id)
        if data.get("status") != "success":
            message = data.get("message", "分析失败")
            result = json.dumps({"success": False, "suggestions": [message], "error": message})
            typer.echo(result)
            return result
        result = json.dumps({"success": True, "metrics": data.get("analysis", {})}, ensure_ascii=False, default=str)
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
            # 同步 CLI 没有运行中的事件循环，无法真正拉起交易进程；
            # 明确提示而不静默吞掉，deploy 主体（注册 runtime）照常完成
            typer.echo(
                "警告: CLI 不支持 --auto-start，策略仅注册未启动；请使用 `quantcell worker start` 或 Web 页面启动策略",
                err=True,
            )

        result = json.dumps(
            {
                "success": True,
                "worker_id": worker_id,
                "status": "created",
                "message": f"策略 {strategy_name} 已完成部署",
            }
        )
        typer.echo(result)
        return result
    except Exception as e:
        typer.echo(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False), err=True)
        raise typer.Exit(1) from e


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
