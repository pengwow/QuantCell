#!/usr/bin/env python3
"""
RL 训练命令行工具

提供RL训练、模型管理、风控检查等功能。
此模块为薄封装层，核心逻辑调用Service层。

使用示例:
    # 从本地数据执行RL训练
    python scripts/rl_cli.py train --symbol BTCUSDT --interval 1h --algorithm ppo --timesteps 1000

    # 列出已注册模型
    python scripts/rl_cli.py models

    # 风控检查
    python scripts/rl_cli.py check --order '{"symbol":"BTC-USDT","side":"Buy","quantity":0.1,"price":50000}' --portfolio '{"cash":{"USD":200000}}'
"""

import sys
import json
from pathlib import Path
from typing import Optional

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import typer
from typing_extensions import Annotated

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

app = typer.Typer(
    name="rl-cli",
    help="RL 训练命令行工具",
    add_completion=False,
)


@app.command()
def train(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对 (如 BTCUSDT)")] = "",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期 (如 1h, 4h, 1d)")] = "1h",
    candle_type: Annotated[str, typer.Option("--candle-type", help="市场类型 (spot/future)")] = "spot",
    start: Annotated[Optional[str], typer.Option("--start", help="开始时间 (YYYY-MM-DD)")] = None,
    end: Annotated[Optional[str], typer.Option("--end", help="结束时间 (YYYY-MM-DD)")] = None,
    algorithm: Annotated[str, typer.Option("--algorithm", "-a", help="算法 (ppo/sac/dqn)")] = "ppo",
    timesteps: Annotated[int, typer.Option("--timesteps", "-t", help="训练步数")] = 1000,
    reward: Annotated[str, typer.Option("--reward", "-r", help="奖励函数 (pnl/sharpe/sortino)")] = "pnl",
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="模型名称")] = None,
    walk_forward: Annotated[bool, typer.Option("--walk-forward", "-w", help="启用Walk-Forward验证")] = False,
    wf_splits: Annotated[int, typer.Option("--wf-splits", help="WF分割数")] = 5,
):
    """执行RL训练（从本地Parquet数据）"""
    from services.rl_service import RLService, RLTrainConfig

    if not symbol:
        typer.echo("错误: 必须指定 --symbol (如 --symbol BTCUSDT)", err=True)
        raise typer.Exit(code=1)

    svc = RLService()

    config = RLTrainConfig(
        algorithm=algorithm,
        symbol=symbol,
        interval=interval,
        candle_type=candle_type,
        start=start,
        end=end,
        total_timesteps=timesteps,
        reward_type=reward,
        model_name=name or f"{algorithm}_{timesteps}",
        walk_forward=walk_forward,
        wf_splits=wf_splits,
    )

    typer.echo(f"[RL CLI] 开始训练: symbol={symbol}, algorithm={config.algorithm}, timesteps={config.total_timesteps}, reward={config.reward_type}")
    result = svc.train(config)

    typer.echo(f"\n{'='*50}")
    typer.echo(f"训练完成!")
    typer.echo(f"{'='*50}")
    typer.echo(f"模型 ID:      {result.model_id}")
    typer.echo(f"模型路径:     {result.model_path}")
    typer.echo(f"训练步数:     {result.metrics.get('steps', 0)}")
    typer.echo(f"耗时:         {result.metrics.get('elapsed_seconds', 0):.1f}秒")

    if result.walk_forward:
        wf = result.walk_forward
        agg = wf.get("aggregate", {})
        mean = agg.get("mean", {})
        typer.echo(f"\nWalk-Forward 结果 ({wf.get('n_splits', '?')} splits, {wf.get('mode', '?')}):")
        typer.echo(f"  有效fold数:   {agg.get('n_valid_folds', 0)}")
        typer.echo(f"  平均PnL:      {mean.get('total_pnl', 0):.2f}")
        typer.echo(f"  平均Sharpe:    {mean.get('sharpe_ratio', 0):.4f}")
        typer.echo(f"  平均回撤:     {mean.get('max_drawdown_pct', 0):.2f}%")
        typer.echo(f"  平均胜率:     {mean.get('win_rate', 0):.2%}")

    typer.echo(f"{'='*50}")


@app.command()
def models():
    """列出已保存的RL模型"""
    from services.rl_service import RLService

    svc = RLService()
    saved = svc.list_saved_models()

    if not saved:
        typer.echo("暂无已保存模型")
        return

    typer.echo(f"\n{'='*60}")
    typer.echo(f"已保存模型 ({len(saved)} 个)")
    typer.echo(f"{'='*60}")
    for m in saved:
        typer.echo(f"  - {m['name']} ({m['size_mb']}MB)")
    typer.echo(f"{'='*60}")
    typer.echo(f"保存目录: {svc._models_dir if hasattr(svc, '_models_dir') else 'data/models'}")


@app.command()
def backtest(
    model: Annotated[str, typer.Option("--model", "-m", help="模型路径 (.zip)")],
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对 (如 BTCUSDT)")] = "BTCUSDT",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期")] = "1h",
    initial_capital: Annotated[float, typer.Option("--cash", help="初始资金")] = 100_000.0,
    reward: Annotated[str, typer.Option("--reward", "-r", help="奖励类型 (pnl/sharpe/sortino)")] = "pnl",
):
    """用训练好的RL模型通过axon_quant TradingEnv回测"""
    from services.rl_service import RLService

    svc = RLService()
    typer.echo(f"[RL Backtest] model={model}, symbol={symbol}, interval={interval}")

    result = svc.run_backtest(
        model_path=model, symbol=symbol, interval=interval,
        initial_capital=initial_capital, reward_type=reward,
    )

    typer.echo(f"\n{'='*60}")
    typer.echo(f"回测结果: {symbol} {interval}")
    typer.echo(f"{'='*60}")
    for k, v in result.items():
        if isinstance(v, float):
            typer.echo(f"  {k:.<30} {v:>12.4f}")
        else:
            typer.echo(f"  {k:.<30} {v}")
    typer.echo(f"{'='*60}")


@app.command()
def check(
    order: Annotated[str, typer.Option("--order", help='订单JSON: \'{"symbol":"BTC-USDT","side":"Buy","quantity":0.1,"price":50000}\'')],
    portfolio: Annotated[str, typer.Option("--portfolio", help='组合JSON: \'{"cash":{"USD":200000}}\'')],
    max_order_value: Annotated[float, typer.Option("--max-order-value", help="最大订单价值")] = 100000.0,
):
    """风控检查"""
    from services.risk_service import RiskService

    svc = RiskService({"max_order_value": max_order_value})

    try:
        order_dict = json.loads(order)
        portfolio_dict = json.loads(portfolio)
    except json.JSONDecodeError as e:
        typer.echo(f"JSON解析失败: {e}", err=True)
        raise typer.Exit(code=1)

    result = svc.check_order(order_dict, portfolio_dict)

    if result["passed"]:
        typer.echo("✓ 风控检查通过")
    else:
        typer.echo(f"✗ 风控检查拒绝: {result['reason']}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
