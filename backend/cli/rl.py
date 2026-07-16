#!/usr/bin/env python3
"""RL 命令行工具

使用示例:
    # 训练模型
    python scripts/rl_cli.py train --symbol BTCUSDT --algorithm ppo --timesteps 5000

    # 列出已训练模型
    python scripts/rl_cli.py models

    # 回测模型
    python scripts/rl_cli.py backtest --model data/rl_models/BTCUSDT_ppo_xxx.zip --symbol BTCUSDT

    # 一键启动完整生命周期（训练→回测→评估→重训练）
    python scripts/rl_cli.py lifecycle --symbol BTCUSDT
"""

import sys
from pathlib import Path
from typing import Optional

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import typer
from typing_extensions import Annotated

app = typer.Typer(name="rl-cli", help="RL 命令行工具", add_completion=False)


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
        symbol=symbol, algorithm=algorithm, timesteps=timesteps,
        learning_rate=learning_rate, reward=reward, interval=interval,
        lookback_days=lookback_days, initial_capital=initial_capital,
        transaction_cost=transaction_cost, output_name=name,
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


@app.command()
def lifecycle(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")] = "BTCUSDT",
    interval: Annotated[str, typer.Option("--interval", "-i", help="K线周期")] = "15m",
    train_timesteps: Annotated[int, typer.Option("--train-steps", help="初始训练步数")] = 30000,
    retrain_timesteps: Annotated[int, typer.Option("--retrain-steps", help="重训练步数")] = 10000,
    eval_days: Annotated[int, typer.Option("--eval-days", help="评估数据天数")] = 30,
    lookback_days: Annotated[int, typer.Option("--days", help="训练数据天数")] = 90,
    check_hours: Annotated[int, typer.Option("--check-hours", help="检查间隔(小时)")] = 24,
    max_retrain_age: Annotated[int, typer.Option("--max-age", help="模型最大存活天数")] = 7,
    min_sharpe: Annotated[float, typer.Option("--min-sharpe", help="最低夏普比率")] = 0.5,
    max_drawdown: Annotated[float, typer.Option("--max-dd", help="最大回撤阈值(%)")] = 5.0,
):
    """一键启动完整生命周期: 训练 → 回测 → 评估 → 重训练（循环）"""
    from rl.lifecycle import RLLifecycle, LifecycleConfig

    config = LifecycleConfig(
        symbol=symbol, interval=interval,
        train_timesteps=train_timesteps,
        retrain_timesteps=retrain_timesteps,
        eval_days=eval_days, lookback_days=lookback_days,
        check_interval_hours=check_hours,
        max_retrain_age_days=max_retrain_age,
        min_sharpe=min_sharpe,
        max_drawdown_pct=max_drawdown,
    )

    lifecycle = RLLifecycle(config)

    typer.echo(f"{'='*55}")
    typer.echo(f"  RL 自动迭代生命周期")
    typer.echo(f"{'='*55}")
    typer.echo(f"  品种:       {symbol} {interval}")
    typer.echo(f"  初始训练:   {train_timesteps} 步")
    typer.echo(f"  重训练:     {retrain_timesteps} 步")
    typer.echo(f"  检查间隔:   {check_hours} 小时")
    typer.echo(f"  夏普阈值:   {min_sharpe}")
    typer.echo(f"  回撤阈值:   {max_drawdown}%")
    typer.echo(f"{'='*55}")

    # Phase 1: 初始训练
    typer.echo(f"\n[1/4] 初始训练 ({train_timesteps} 步)...")
    model_path = lifecycle.run_initial_training()
    typer.echo(f"  ✅ 模型: {model_path}")

    # Phase 2: 回测
    typer.echo(f"\n[2/4] 回测评估...")
    bt_result = lifecycle.run_backtest(model_path)
    typer.echo(f"  PnL:   ${bt_result['total_pnl']:>+.2f}")
    typer.echo(f"  交易:  {bt_result['fills']} 笔")
    typer.echo(f"  夏普:  {bt_result['sharpe_ratio']:.4f}")

    # Phase 3: 评估决策
    typer.echo(f"\n[3/4] 评估决策...")
    from rl.lifecycle import ModelMetrics
    metrics = ModelMetrics(
        model_name=Path(model_path).stem,
        timestamp="",
        pnl=bt_result.get("total_pnl", 0),
        trades=bt_result.get("fills", 0),
        sharpe=bt_result.get("sharpe_ratio", 0),
        max_drawdown=bt_result.get("max_drawdown", 0),
    )
    decision = lifecycle.evaluate_and_decide(metrics)
    typer.echo(f"  决策: {decision}")

    # Phase 4: 重训练（如果需要）
    if decision == "retrain":
        typer.echo(f"\n[4/4] 重训练 ({retrain_timesteps} 步)...")
        new_model = lifecycle.retrain(model_path)
        typer.echo(f"  ✅ 新模型: {new_model}")
    else:
        typer.echo(f"\n[4/4] 无需重训练，模型表现良好")

    # 汇总
    typer.echo(f"\n{'='*55}")
    typer.echo(f"  生命周期完成")
    typer.echo(f"{'='*55}")
    typer.echo(f"  当前模型: {model_path}")
    typer.echo(f"  回测 PnL: ${bt_result['total_pnl']:>+.2f}")
    typer.echo(f"  交易次数: {bt_result['fills']}")
    typer.echo(f"  夏普比率: {bt_result['sharpe_ratio']:.4f}")
    typer.echo(f"{'='*55}")

    if check_hours > 0:
        typer.echo(f"\n💡 提示: 使用 --check-hours 0 只运行一次")
        typer.echo(f"   设置 --check-hours 24 可启动自动循环重训练")


if __name__ == "__main__":
    app()
