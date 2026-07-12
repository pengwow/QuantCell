#!/usr/bin/env python3
"""RL 训练命令行工具

使用示例:
    # 训练模型
    python scripts/rl_cli.py train --symbol BTCUSDT --algorithm ppo --timesteps 5000

    # 列出已训练模型
    python scripts/rl_cli.py models

    # 回测模型
    python scripts/rl_cli.py backtest --model data/rl_models/BTCUSDT_ppo_xxx.zip --symbol BTCUSDT
"""

import sys
from pathlib import Path
from typing import Optional

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import typer
from typing_extensions import Annotated

app = typer.Typer(name="rl-cli", help="RL 训练命令行工具", add_completion=False)


@app.command()
def train(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")] = "BTCUSDT",
    algorithm: Annotated[str, typer.Option("--algorithm", "-a", help="算法 (ppo/sac/a2c)")] = "ppo",
    timesteps: Annotated[int, typer.Option("--timesteps", "-t", help="训练步数")] = 5000,
    learning_rate: Annotated[float, typer.Option("--lr", help="学习率")] = 3e-4,
    reward: Annotated[str, typer.Option("--reward", "-r", help="奖励函数 (pnl/sharpe/sortino)")] = "pnl",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期")] = "1h",
    lookback_days: Annotated[int, typer.Option("--days", help="回看天数")] = 90,
    initial_capital: Annotated[float, typer.Option("--cash", help="初始资金")] = 100_000,
    transaction_cost: Annotated[float, typer.Option("--fee", help="交易费率")] = 0.001,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="模型名称")] = None,
):
    """训练 RL 模型"""
    from rl.service import RLService
    from rl.models import RLTrainConfig

    typer.echo(f"[RL] 开始训练: {symbol} {algorithm} {timesteps}步")
    typer.echo(f"  奖励函数: {reward} | 学习率: {learning_rate} | 数据: {interval} x {lookback_days}天")

    config = RLTrainConfig(
        symbol=symbol,
        algorithm=algorithm,
        timesteps=timesteps,
        learning_rate=learning_rate,
        reward=reward,
        interval=interval,
        lookback_days=lookback_days,
        initial_capital=initial_capital,
        transaction_cost=transaction_cost,
        output_name=name,
    )

    svc = RLService()
    result = svc.train(config)

    typer.echo(f"\n{'='*50}")
    typer.echo(f"训练完成!")
    typer.echo(f"{'='*50}")
    typer.echo(f"  模型名称:     {result['model_name']}")
    typer.echo(f"  模型路径:     {result['model_path']}")
    typer.echo(f"  训练步数:     {result['total_timesteps']}")
    typer.echo(f"  耗时:         {result['training_time_secs']:.1f}秒")
    typer.echo(f"  评估奖励:     {result.get('eval_reward_mean', 0):.4f} ± {result.get('eval_reward_std', 0):.4f}")
    typer.echo(f"{'='*50}")


@app.command()
def models():
    """列出已训练模型"""
    from rl.service import RLService

    svc = RLService()
    saved = svc.list_models()

    if not saved:
        typer.echo("暂无已训练模型")
        return

    typer.echo(f"\n已训练模型 ({len(saved)} 个):")
    typer.echo(f"{'-'*50}")
    for m in saved:
        typer.echo(f"  {m['name']:<40} {m['size_kb']:>6.1f}KB")
    typer.echo(f"{'-'*50}")


@app.command()
def backtest(
    model: Annotated[str, typer.Option("--model", "-m", help="模型路径 (.zip)")],
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")] = "BTCUSDT",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期")] = "1h",
    lookback_days: Annotated[int, typer.Option("--days", help="回看天数")] = 90,
):
    """用训练好的模型回测"""
    from rl.service import RLService

    typer.echo(f"[RL Backtest] model={model}, symbol={symbol}")

    svc = RLService()
    result = svc.backtest(model, symbol, interval, lookback_days)

    typer.echo(f"\n{'='*50}")
    typer.echo(f"回测结果: {symbol} {interval}")
    typer.echo(f"{'='*50}")
    typer.echo(f"  总盈亏:       ${result['total_pnl']:>+10,.2f}")
    typer.echo(f"  最终净值:     ${result['final_nav']:>10,.2f}")
    typer.echo(f"  夏普比率:     {result['sharpe_ratio']:>10.4f}")
    typer.echo(f"  最大回撤:     ${result['max_drawdown']:>10,.2f}")
    typer.echo(f"  胜率:         {result['win_rate']:>10.2%}")
    typer.echo(f"  成交次数:     {result['fills']:>10}")
    typer.echo(f"  总手续费:     ${result['total_fees']:>10,.2f}")
    typer.echo(f"{'='*50}")


if __name__ == "__main__":
    app()
