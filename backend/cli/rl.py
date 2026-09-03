#!/usr/bin/env python3
"""RL 命令行工具

使用示例:
    # 训练模型
    uv run python -m cli.rl train --symbol BTCUSDT --algorithm ppo --timesteps 5000

    # 列出已训练模型
    uv run python -m cli.rl models

    # 回测模型
    uv run python -m cli.rl backtest --model data/models/BTCUSDT_ppo_xxx.zip --symbol BTCUSDT

    # 一键启动完整生命周期（训练→回测→评估→重训练）
    uv run python -m cli.rl lifecycle --symbol BTCUSDT
"""

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from typing import Annotated

import typer

from services.rl_service import RLService, RLTrainConfig

app = typer.Typer(name="rl-cli", help="RL 命令行工具", add_completion=False)


@app.command()
def train(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")] = "BTCUSDT",
    algorithm: Annotated[str, typer.Option("--algorithm", "-a", help="算法 (ppo/sac/dqn)")] = "ppo",
    timesteps: Annotated[int, typer.Option("--timesteps", "-t", help="训练步数")] = 5000,
    reward: Annotated[str, typer.Option("--reward", "-r", help="奖励函数 (pnl/sharpe/sortino)")] = "pnl",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期")] = "1h",
    name: Annotated[str | None, typer.Option("--name", "-n", help="模型名称")] = None,
    walk_forward: Annotated[bool, typer.Option("--walk-forward", "-wf", help="启用 Walk-Forward 验证")] = False,
):
    """训练 RL 模型"""
    typer.echo(f"[RL] 开始训练: {symbol} {algorithm} {timesteps}步")
    typer.echo(f"  奖励函数: {reward} | 数据: {interval}")

    config = RLTrainConfig(
        symbol=symbol,
        algorithm=algorithm,
        interval=interval,
        total_timesteps=timesteps,
        reward_type=reward,
        model_name=name or f"{symbol}_{algorithm}",
        walk_forward=walk_forward,
    )

    svc = RLService()
    result = svc.train(config)

    typer.echo(f"\n{'=' * 50}")
    typer.echo("训练完成!")
    typer.echo(f"{'=' * 50}")
    typer.echo(f"  模型ID:       {result.model_id}")
    typer.echo(f"  模型路径:     {result.model_path}")
    typer.echo(f"  训练步数:     {result.metrics.get('steps')}")
    typer.echo(f"  算法:         {result.metrics.get('algorithm')}")
    typer.echo(f"  耗时:         {result.metrics.get('elapsed_seconds')}秒")
    if result.walk_forward:
        agg = result.walk_forward.get("aggregate", {})
        typer.echo(
            f"  Walk-Forward: {agg.get('n_valid_folds', 0)} folds, mean sharpe={agg.get('mean', {}).get('sharpe_ratio')}"
        )
    typer.echo(f"{'=' * 50}")


@app.command()
def models():
    """列出已训练模型"""
    svc = RLService()
    saved = svc.list_saved_models()

    if not saved:
        typer.echo("暂无已训练模型")
        return

    typer.echo(f"\n已训练模型 ({len(saved)} 个):")
    typer.echo(f"{'-' * 60}")
    for m in saved:
        typer.echo(f"  {m['name']:<44} {m['size_mb']:>6.2f}MB")
    typer.echo(f"{'-' * 60}")


@app.command()
def backtest(
    model: Annotated[str, typer.Option("--model", "-m", help="模型路径 (.zip)")],
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")] = "BTCUSDT",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期")] = "1h",
    reward: Annotated[str, typer.Option("--reward", "-r", help="奖励函数")] = "pnl",
):
    """用训练好的模型回测"""
    typer.echo(f"[RL Backtest] model={model}, symbol={symbol}")

    svc = RLService()
    result = svc.run_backtest(model, symbol, interval, reward_type=reward)

    typer.echo(f"\n{'=' * 50}")
    typer.echo(f"回测结果: {symbol} {interval}")
    typer.echo(f"{'=' * 50}")
    typer.echo(f"  总盈亏:       ${result['total_pnl']:>+10,.2f}")
    typer.echo(f"  收益率:       {result['total_return_pct']:>10.4f}%")
    typer.echo(f"  夏普比率:     {result['sharpe_ratio']:>10.4f}")
    typer.echo(f"  最大回撤:     {result['max_drawdown_pct']:>10.4f}%")
    typer.echo(f"  胜率:         {result['win_rate']:>10.2%}")
    typer.echo(f"  交易次数:     {result['num_trades']:>10}")
    typer.echo(f"  盈亏比:       {result['profit_factor']:>10.4f}")
    typer.echo(f"{'=' * 50}")


@app.command()
def lifecycle(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")] = "BTCUSDT",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期")] = "1h",
    algorithm: Annotated[str, typer.Option("--algorithm", "-a", help="算法")] = "ppo",
    train_timesteps: Annotated[int, typer.Option("--train-steps", help="初始训练步数")] = 30000,
    retrain_timesteps: Annotated[int, typer.Option("--retrain-steps", help="重训练步数")] = 10000,
    min_sharpe: Annotated[float, typer.Option("--min-sharpe", help="最低夏普比率")] = 0.5,
    max_drawdown: Annotated[float, typer.Option("--max-dd", help="最大回撤阈值(%)")] = 5.0,
):
    """一键启动完整生命周期: 训练 → 回测 → 评估 → 重训练"""
    from rl.lifecycle import LifecycleConfig, RLLifecycle

    config = LifecycleConfig(
        symbol=symbol,
        interval=interval,
        algorithm=algorithm,
        train_timesteps=train_timesteps,
        retrain_timesteps=retrain_timesteps,
        min_sharpe=min_sharpe,
        max_drawdown_pct=max_drawdown,
    )

    typer.echo(f"{'=' * 55}")
    typer.echo("  RL 自动迭代生命周期")
    typer.echo(f"{'=' * 55}")
    typer.echo(f"  品种:       {symbol} {interval}")
    typer.echo(f"  初始训练:   {train_timesteps} 步")
    typer.echo(f"  重训练:     {retrain_timesteps} 步")
    typer.echo(f"  夏普阈值:   {min_sharpe}")
    typer.echo(f"  回撤阈值:   {max_drawdown}%")
    typer.echo(f"{'=' * 55}")

    lifecycle = RLLifecycle(config)
    summary = lifecycle.run_once()

    bt = summary["backtest"]
    typer.echo(f"\n{'=' * 55}")
    typer.echo("  生命周期完成")
    typer.echo(f"{'=' * 55}")
    typer.echo(f"  当前模型: {summary['model_path']}")
    typer.echo(f"  决策:     {summary['decision']}")
    typer.echo(f"  回测 PnL: ${bt.get('total_pnl', 0):>+.2f}")
    typer.echo(f"  交易次数: {bt.get('num_trades', 0)}")
    typer.echo(f"  夏普比率: {bt.get('sharpe_ratio', 0):.4f}")
    typer.echo(f"{'=' * 55}")


if __name__ == "__main__":
    app()
