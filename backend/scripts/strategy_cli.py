#!/usr/bin/env python3
"""
策略管理命令行工具

提供策略的增删改查、生成、分析、优化、诊断、部署等功能。
此模块为薄封装层，核心逻辑调用Service层。

使用示例:
    # 列出所有策略
    python scripts/strategy_cli.py list

    # 查看策略详情
    python scripts/strategy_cli.py info 1

    # 生成策略
    python scripts/strategy_cli.py generate --requirement "双均线交叉策略" --name sma_cross

    # 分析回测结果
    python scripts/strategy_cli.py analyze --backtest-id xxx

    # 优化策略参数
    python scripts/strategy_cli.py optimize --strategy sma_cross --params '{"fast": [5,10,15], "slow": [20,30,40]}'

    # 诊断策略问题
    python scripts/strategy_cli.py diagnose --strategy sma_cross

    # 部署策略到Worker
    python scripts/strategy_cli.py deploy --strategy sma_cross --symbols BTCUSDT
"""

import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import typer
from typing_extensions import Annotated

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 创建主应用
app = typer.Typer(
    name="strategy-cli",
    help="策略管理命令行工具",
    add_completion=False,
)


def list_strategies(db_session=None) -> str:
    """
    列出所有策略

    Args:
        db_session: 数据库会话（可选，不传则内部创建）

    Returns:
        str: 策略列表或错误信息（以"错误:"开头）
    """
    try:
        from strategy.models import Strategy
        from utils.db_session import use_db_session

        with use_db_session(db_session) as db:
            strategies = db.query(Strategy).all()
            if not strategies:
                return "系统中暂无策略"

            lines = ["可用策略列表:\n"]
            for s in strategies:
                lines.append(
                    f"ID: {s.id}, 名称: {s.name}, "
                    f"类型: {s.strategy_type or 'N/A'}, "
                    f"状态: {'已激活' if s.is_active else '未激活'}"
                )
            return "\n".join(lines)
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        return f"错误: 获取策略列表失败: {e}"


def get_strategy_detail(strategy_id: int, db_session=None) -> str:
    """
    获取策略详情

    Args:
        strategy_id: 策略ID
        db_session: 数据库会话（可选）

    Returns:
        str: 策略详情或错误信息
    """
    try:
        from strategy.models import Strategy
        from utils.db_session import use_db_session

        with use_db_session(db_session) as db:
            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if not strategy:
                return f"策略 ID {strategy_id} 不存在"

            return (
                f"策略详情:\n"
                f"ID: {strategy.id}\n"
                f"名称: {strategy.name}\n"
                f"描述: {strategy.description or 'N/A'}\n"
                f"类型: {strategy.strategy_type or 'N/A'}\n"
                f"状态: {'已激活' if strategy.is_active else '未激活'}\n"
                f"创建时间: {strategy.created_at}\n"
                f"更新时间: {strategy.updated_at}"
            )
    except Exception as e:
        logger.error(f"获取策略详情失败: {e}")
        return f"错误: 获取策略详情失败: {e}"


def generate_strategy(
    requirement: str,
    strategy_name: str,
    indicators: Optional[str] = None,
) -> str:
    """
    根据自然语言描述生成量化策略代码

    Args:
        requirement: 策略需求描述
        strategy_name: 策略名称
        indicators: 自定义指标配置（可选），JSON格式

    Returns:
        str: JSON格式的结果
    """
    try:
        import asyncio
        from ai_model.strategy_generator import StrategyGenerator
        from ai_model.code_validator import CodeValidator
        from ai_model.config_utils import get_default_provider_and_models

        strategies_dir = backend_path / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)
        file_path = strategies_dir / f"{strategy_name}.py"

        if file_path.exists():
            return json.dumps(
                {
                    "success": False,
                    "code": None,
                    "file_path": str(file_path),
                    "validation_errors": [f"策略文件已存在: {file_path}"],
                },
                ensure_ascii=False,
            )

        provider_info = get_default_provider_and_models()
        if not provider_info:
            return json.dumps(
                {
                    "success": False,
                    "code": None,
                    "file_path": None,
                    "validation_errors": ["未配置AI模型，请先在设置中配置模型提供商"],
                },
                ensure_ascii=False,
            )

        provider = provider_info["provider"]
        enabled_models = provider_info.get("enabled_models", [])
        model_id = enabled_models[0]["id"] if enabled_models else provider.get("id", "gpt-4")
        model_name = enabled_models[0].get("model_name") if enabled_models else None

        generator = StrategyGenerator(
            api_key=provider.get("api_key", ""),
            api_host=provider.get("api_host"),
            model_id=model_id,
            model_name=model_name,
        )

        template_vars = {}
        if indicators:
            template_vars["indicators"] = indicators

        result = asyncio.run(
            asyncio.to_thread(generator.generate_strategy, requirement, **template_vars)
        )

        if not result.get("success"):
            return json.dumps(
                {
                    "success": False,
                    "code": None,
                    "file_path": None,
                    "validation_errors": [result.get("error", "策略生成失败")],
                },
                ensure_ascii=False,
            )

        code = result.get("code", "")

        validator = CodeValidator()
        validation = validator.validate(code)
        errors = validation.get("errors", [])
        error_messages = [e.to_dict() if hasattr(e, "to_dict") else str(e) for e in errors]

        if error_messages:
            return json.dumps(
                {
                    "success": False,
                    "code": code,
                    "file_path": None,
                    "validation_errors": error_messages,
                },
                ensure_ascii=False,
            )

        file_path.write_text(code, encoding="utf-8")

        return json.dumps(
            {
                "success": True,
                "code": code,
                "file_path": str(file_path),
                "validation_errors": [],
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"生成策略失败: {e}")
        return json.dumps(
            {
                "success": False,
                "code": None,
                "file_path": None,
                "validation_errors": [str(e)],
            },
            ensure_ascii=False,
        )


def analyze_backtest_result(
    backtest_id: Optional[str] = None,
    result_file: Optional[str] = None,
    result_data: Optional[str] = None,
) -> str:
    """
    分析回测结果，解读关键指标并给出优化建议

    Args:
        backtest_id: 回测任务ID
        result_file: 回测结果JSON文件路径
        result_data: 直接传入的回测结果JSON字符串

    Returns:
        str: JSON格式的分析结果
    """
    try:
        from backtest.result_analysis import ResultAnalyzer

        raw_data = None

        if backtest_id:
            from utils.db_session import get_db_session
            from backtest.models import BacktestResult

            with get_db_session() as db:
                record = db.query(BacktestResult).filter(BacktestResult.id == backtest_id).first()
                if not record:
                    return json.dumps(
                        {"success": False, "metrics": None, "suggestions": [f"回测结果 {backtest_id} 不存在"]},
                        ensure_ascii=False,
                    )
                raw_data = record.get_metrics_dict()
        elif result_file:
            with open(result_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        elif result_data:
            raw_data = json.loads(result_data)
        else:
            return json.dumps(
                {"success": False, "metrics": None, "suggestions": ["请提供 backtest_id、result_file 或 result_data 中的至少一个"]},
                ensure_ascii=False,
            )

        analyzer = ResultAnalyzer()
        metrics = analyzer.analyze(raw_data) if isinstance(raw_data, dict) and "portfolio" not in raw_data else raw_data

        # 基于关键指标生成优化建议
        suggestions = []
        m = metrics if isinstance(metrics, dict) else {}

        sharpe = m.get("sharpe_ratio") or m.get("avg_sharpe", 0)
        if sharpe and float(sharpe) < 1.0:
            suggestions.append("夏普比率偏低，建议增加趋势过滤器或优化入场时机")

        max_dd = m.get("max_drawdown", 0)
        if max_dd and float(max_dd) > 0.2:
            suggestions.append("最大回撤过大，建议收紧止损或降低仓位")

        win_rate = m.get("win_rate") or m.get("avg_win_rate", 0)
        if win_rate and float(win_rate) < 0.4:
            suggestions.append("胜率较低，建议增加确认信号或优化出场逻辑")

        total_pnl = m.get("total_pnl", 0)
        if total_pnl and float(total_pnl) < 0:
            suggestions.append("总盈亏为负，建议检查策略逻辑是否符合市场特征")

        profit_factor = m.get("profit_factor", 0)
        if profit_factor and float(profit_factor) < 1.0:
            suggestions.append("盈亏比不合理，建议优化止盈止损比例")

        if not suggestions:
            suggestions.append("当前指标表现良好，可考虑进一步优化参数以提升收益")

        return json.dumps({"success": True, "metrics": metrics, "suggestions": suggestions}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"分析回测结果失败: {e}")
        return json.dumps({"success": False, "metrics": None, "suggestions": [str(e)]}, ensure_ascii=False)


def optimize_strategy_params(
    strategy_name: str,
    param_ranges: str,
    symbols: str = "BTCUSDT",
    timeframe: str = "1h",
    metric: str = "sharpe_ratio",
    max_iterations: int = 50,
) -> str:
    """
    通过网格搜索自动寻找最优策略参数

    Args:
        strategy_name: 策略名称
        param_ranges: 参数搜索范围，JSON格式
        symbols: 交易对列表，逗号分隔
        timeframe: 时间周期
        metric: 优化目标指标
        max_iterations: 最大迭代次数

    Returns:
        str: JSON格式的优化结果
    """
    try:
        import asyncio
        import itertools
        from backtest.service import BacktestService

        ranges = json.loads(param_ranges)
        param_names = list(ranges.keys())
        param_values = list(ranges.values())

        combinations = list(itertools.product(*param_values))
        if len(combinations) > max_iterations:
            combinations = combinations[:max_iterations]

        symbol_list = [s.strip() for s in symbols.split(",")]
        service = BacktestService()
        results = []

        for combo in combinations:
            params = dict(zip(param_names, combo))
            try:
                task_id = service.create_task(
                    strategy_name=strategy_name,
                    strategy_params=params,
                    symbols=symbol_list,
                    timeframes=[timeframe],
                    engine_type="default",
                )
                result = asyncio.run(asyncio.to_thread(service.run_backtest, task_id))
                if result:
                    results.append({"params": params, "metrics": result})
            except Exception:
                continue

        results.sort(key=lambda x: x["metrics"].get(metric, float("-inf")), reverse=True)
        top_results = results[:10]

        return json.dumps(
            {"success": True, "total_combinations": len(combinations), "results": top_results},
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"优化策略参数失败: {e}")
        return json.dumps({"success": False, "total_combinations": 0, "results": [], "error": str(e)}, ensure_ascii=False)


def diagnose_strategy(
    strategy_name: str,
    backtest_id: Optional[str] = None,
) -> str:
    """
    诊断策略问题，分析策略亏损原因

    Args:
        strategy_name: 策略名称
        backtest_id: 回测任务ID（可选）

    Returns:
        str: JSON格式的诊断结果
    """
    try:
        strategies_dir = backend_path / "strategies"
        strategy_file = strategies_dir / f"{strategy_name}.py"

        if not strategy_file.exists():
            return json.dumps(
                {
                    "success": False,
                    "code_analysis": None,
                    "trade_analysis": None,
                    "issues": [f"策略文件不存在: {strategy_file}"],
                    "recommendations": [],
                },
                ensure_ascii=False,
            )

        code = strategy_file.read_text(encoding="utf-8")

        # 静态分析：检查止损逻辑
        has_stop_loss = any(kw in code for kw in ["stop_loss", "止损", "SL", "close_position"])
        # 静态分析：检查仓位管理
        has_position_sizing = any(kw in code for kw in ["position_size", "仓位", "size", "amount"])
        # 静态分析：检查风险管理
        has_risk_management = any(kw in code for kw in ["max_drawdown", "risk", "max_position"])

        code_analysis = {
            "has_stop_loss": has_stop_loss,
            "has_position_sizing": has_position_sizing,
            "has_risk_management": has_risk_management,
        }

        issues = []
        recommendations = []
        if not has_stop_loss:
            issues.append("未检测到止损逻辑，可能导致亏损无限扩大")
            recommendations.append("建议添加止损机制，如固定比例止损或追踪止损")
        if not has_position_sizing:
            issues.append("未检测到仓位管理逻辑，可能导致仓位过大或过小")
            recommendations.append("建议添加仓位管理，根据风险承受能力动态调整仓位")
        if not has_risk_management:
            issues.append("未检测到风险管理逻辑，缺乏最大回撤控制")
            recommendations.append("建议添加最大回撤限制和单笔最大亏损控制")

        trade_analysis = None
        if backtest_id:
            from utils.db_session import get_db_session
            from backtest.models import BacktestResult

            with get_db_session() as db:
                record = db.query(BacktestResult).filter(BacktestResult.id == backtest_id).first()
                if record:
                    metrics = record.get_metrics_dict()
                    trades = record.get_trades_list()
                    # 连续亏损分析
                    max_consecutive_losses = 0
                    current_losses = 0
                    for t in trades:
                        pnl = t.get("pnl", 0)
                        if pnl and float(pnl) < 0:
                            current_losses += 1
                            max_consecutive_losses = max(max_consecutive_losses, current_losses)
                        else:
                            current_losses = 0

                    trade_analysis = {
                        "total_trades": len(trades),
                        "max_consecutive_losses": max_consecutive_losses,
                        "max_drawdown": metrics.get("max_drawdown", 0),
                        "win_rate": metrics.get("win_rate", 0),
                        "profit_factor": metrics.get("profit_factor", 0),
                    }

                    if max_consecutive_losses > 5:
                        issues.append(f"连续亏损次数过多({max_consecutive_losses}次)，策略稳定性不足")
                        recommendations.append("建议增加过滤条件减少连续亏损，或设置连续亏损后的暂停机制")

        return json.dumps(
            {
                "success": True,
                "code_analysis": code_analysis,
                "trade_analysis": trade_analysis,
                "issues": issues,
                "recommendations": recommendations,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"诊断策略失败: {e}")
        return json.dumps(
            {
                "success": False,
                "code_analysis": None,
                "trade_analysis": None,
                "issues": [str(e)],
                "recommendations": [],
            },
            ensure_ascii=False,
        )


def deploy_strategy(
    strategy_name: str,
    symbols: str,
    strategy_file_name: Optional[str] = None,
    exchange: str = "binance",
    timeframe: str = "1h",
    initial_capital: float = 100000,
    trading_mode: str = "demo",
    auto_start: bool = False,
) -> str:
    """
    将策略部署到Worker实盘运行

    Args:
        strategy_name: 策略名称
        symbols: 交易对列表，逗号分隔
        strategy_file_name: 策略文件名（不含.py后缀）
        exchange: 交易所名称
        timeframe: 时间周期
        initial_capital: 初始资金
        trading_mode: 交易模式：demo(模拟)/live(实盘)
        auto_start: 是否自动启动

    Returns:
        str: JSON格式的部署结果
    """
    try:
        from worker.core_service import WorkerCoreService
        from worker.schemas import WorkerCreate

        symbol_list = [s.strip() for s in symbols.split(",")]
        file_name = strategy_file_name or strategy_name

        data = WorkerCreate(
            name=f"{strategy_name}_worker",
            strategy_name=strategy_name,
            strategy_file_name=f"{file_name}.py" if not file_name.endswith(".py") else file_name,
            exchange=exchange,
            symbols=symbol_list,
            timeframe=timeframe,
            trading_mode=trading_mode,
        )

        service = WorkerCoreService()
        worker = service.create_worker(data)
        worker_id = worker.get("id") if isinstance(worker, dict) else getattr(worker, "id", None)

        if auto_start and worker_id:
            from worker.state import nautilus_system
            if nautilus_system:
                nautilus_system.start_strategy(str(worker_id))

        status = "running" if auto_start else "created"
        return json.dumps(
            {
                "success": True,
                "worker_id": worker_id,
                "status": status,
                "message": f"策略 {strategy_name} 已部署为Worker",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"部署策略失败: {e}")
        return json.dumps(
            {
                "success": False,
                "worker_id": None,
                "status": "failed",
                "message": str(e),
            },
            ensure_ascii=False,
        )


# ==================== CLI 命令 ====================

@app.command("list")
def cli_list():
    """列出所有策略"""
    result = list_strategies()
    typer.echo(result)


@app.command("info")
def cli_info(
    strategy_id: Annotated[int, typer.Argument(help="策略 ID")],
):
    """查看策略详情"""
    result = get_strategy_detail(strategy_id)
    typer.echo(result)


@app.command("generate")
def cli_generate(
    requirement: Annotated[str, typer.Option("--requirement", "-r", help="策略需求描述")],
    name: Annotated[str, typer.Option("--name", "-n", help="策略名称")],
    indicators: Annotated[Optional[str], typer.Option("--indicators", "-i", help="自定义指标配置 JSON")] = None,
):
    """生成策略代码"""
    result = generate_strategy(requirement, name, indicators)
    data = json.loads(result)
    if data.get("success"):
        typer.echo(f"策略代码已生成并保存到: {data.get('file_path')}")
    else:
        typer.echo(f"生成失败: {data.get('validation_errors', [])}", err=True)
        raise typer.Exit(1)


@app.command("analyze")
def cli_analyze(
    backtest_id: Annotated[Optional[str], typer.Option("--backtest-id", "-b", help="回测任务ID")] = None,
    result_file: Annotated[Optional[str], typer.Option("--result-file", "-f", help="回测结果JSON文件路径")] = None,
    result_data: Annotated[Optional[str], typer.Option("--result-data", "-d", help="直接传入的回测结果JSON字符串")] = None,
):
    """分析回测结果"""
    if not backtest_id and not result_file and not result_data:
        typer.echo("请提供 --backtest-id、--result-file 或 --result-data 中的至少一个", err=True)
        raise typer.Exit(1)

    result = analyze_backtest_result(backtest_id, result_file, result_data)
    typer.echo(result)


@app.command("optimize")
def cli_optimize(
    strategy_name: Annotated[str, typer.Option("--strategy-name", "-s", help="策略名称")],
    param_ranges: Annotated[str, typer.Option("--param-ranges", "-p", help="参数搜索范围 JSON")],
    symbols: Annotated[str, typer.Option("--symbols", help="交易对列表，逗号分隔")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t", help="时间周期")] = "1h",
    metric: Annotated[str, typer.Option("--metric", "-m", help="优化目标指标")] = "sharpe_ratio",
    max_iterations: Annotated[int, typer.Option("--max-iterations", help="最大迭代次数")] = 50,
):
    """优化策略参数"""
    result = optimize_strategy_params(strategy_name, param_ranges, symbols, timeframe, metric, max_iterations)
    typer.echo(result)


@app.command("diagnose")
def cli_diagnose(
    strategy_name: Annotated[str, typer.Option("--strategy-name", "-s", help="策略名称")],
    backtest_id: Annotated[Optional[str], typer.Option("--backtest-id", "-b", help="回测任务ID")] = None,
):
    """诊断策略问题"""
    result = diagnose_strategy(strategy_name, backtest_id)
    typer.echo(result)


@app.command("deploy")
def cli_deploy(
    strategy_name: Annotated[str, typer.Option("--strategy-name", "-s", help="策略名称")],
    symbols: Annotated[str, typer.Option("--symbols", help="交易对列表，逗号分隔")],
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t", help="时间周期")] = "1h",
    auto_start: Annotated[bool, typer.Option("--auto-start/--no-auto-start", help="是否自动启动")] = False,
):
    """部署策略到Worker"""
    result = deploy_strategy(strategy_name, symbols, exchange=exchange, timeframe=timeframe, auto_start=auto_start)
    data = json.loads(result)
    if data.get("success"):
        typer.echo(f"策略已部署: Worker ID={data.get('worker_id')}, 状态={data.get('status')}")
    else:
        typer.echo(f"部署失败: {data.get('message')}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
