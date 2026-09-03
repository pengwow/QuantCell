"""RL 策略自动迭代生命周期

自动循环：训练 → 回测评估 → 决策 → 重训练 → 循环

使用：python -m rl.lifecycle --symbol BTCUSDT --interval 1h
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from services.rl_service import RLService, RLTrainConfig
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class LifecycleConfig:
    """生命周期配置"""

    symbol: str = "BTCUSDT"
    interval: str = "1h"
    algorithm: str = "ppo"
    reward_type: str = "pnl"
    train_timesteps: int = 30_000
    retrain_timesteps: int = 10_000
    # 重训练触发条件
    min_trades: int = 10  # 最少交易次数
    max_drawdown_pct: float = 5.0  # 最大回撤阈值（%）
    min_sharpe: float = 0.5  # 最低夏普比率
    # 循环控制
    check_interval_hours: int = 24  # 检查间隔（小时）


@dataclass
class ModelMetrics:
    """模型性能指标（来自真实回测）"""

    model_name: str
    timestamp: str = ""
    total_pnl: float = 0.0
    num_trades: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    portfolio_value: float = 100_000.0


class RLLifecycle:
    """RL 策略自动迭代生命周期，统一委托给 services.rl_service 完成真实训练与回测。"""

    def __init__(self, config: LifecycleConfig | None = None):
        self.config = config or LifecycleConfig()
        self._svc = RLService()

    def _make_train_config(self, timesteps: int, model_name: str) -> RLTrainConfig:
        return RLTrainConfig(
            algorithm=self.config.algorithm,
            symbol=self.config.symbol,
            interval=self.config.interval,
            total_timesteps=timesteps,
            reward_type=self.config.reward_type,
            model_name=model_name,
        )

    @staticmethod
    def _to_metrics(model_name: str, bt: dict) -> ModelMetrics:
        """将 services.rl_service.run_backtest 的返回字典转换为 ModelMetrics。"""
        return ModelMetrics(
            model_name=model_name,
            total_pnl=bt.get("total_pnl", 0.0),
            num_trades=bt.get("num_trades", 0),
            win_rate=bt.get("win_rate", 0.0),
            sharpe_ratio=bt.get("sharpe_ratio", 0.0),
            max_drawdown_pct=bt.get("max_drawdown_pct", 0.0),
            portfolio_value=bt.get("initial_capital", 100_000.0) + bt.get("total_pnl", 0.0),
        )

    def run_initial_training(self) -> str:
        """初始训练，返回保存后的模型路径。"""
        logger.info(f"[Phase 1] 初始训练: {self.config.symbol} {self.config.interval}")
        result = self._svc.train(self._make_train_config(self.config.train_timesteps, f"{self.config.symbol}_v1"))
        logger.info(f"[Phase 1] 训练完成: {result.model_path}")
        return result.model_path

    def run_backtest(self, model_path: str) -> dict:
        """用已训练模型做真实回测，返回 services.rl_service.run_backtest 的指标字典。"""
        logger.info(f"[Phase 2] 回测: {model_path}")
        result = self._svc.run_backtest(
            model_path, self.config.symbol, self.config.interval, reward_type=self.config.reward_type
        )
        logger.info(f"[Phase 2] 回测完成: PnL=${result.get('total_pnl', 0.0):.2f}")
        return result

    def evaluate_and_decide(self, metrics: ModelMetrics) -> str:
        """根据真实指标决定下一步。"""
        reasons = []

        if metrics.num_trades < self.config.min_trades:
            reasons.append(f"交易次数不足({metrics.num_trades}<{self.config.min_trades})")

        if abs(metrics.max_drawdown_pct) > self.config.max_drawdown_pct:
            reasons.append(f"回撤过大({metrics.max_drawdown_pct:.1f}%>{self.config.max_drawdown_pct}%)")

        if metrics.sharpe_ratio < self.config.min_sharpe:
            reasons.append(f"夏普过低({metrics.sharpe_ratio:.2f}<{self.config.min_sharpe})")

        if reasons:
            logger.info(f"[Phase 3] 需要重训练: {'; '.join(reasons)}")
            return "retrain"

        logger.info("[Phase 3] 模型表现良好，继续使用")
        return "keep"

    def retrain(self, current_model: str) -> str:
        """用最新数据重训练新模型；仅当新模型夏普更高时才替换当前模型。"""
        logger.info(f"[Phase 4] 重训练: {current_model}")
        new_name = f"{self.config.symbol}_retrain_{int(time.time())}"
        result = self._svc.train(self._make_train_config(self.config.retrain_timesteps, new_name))
        new_model = result.model_path

        old_metrics = self._to_metrics(Path(current_model).stem, self.run_backtest(current_model))
        new_metrics = self._to_metrics(result.model_id, self.run_backtest(new_model))

        if new_metrics.sharpe_ratio > old_metrics.sharpe_ratio:
            logger.info(
                f"[Phase 4] 新模型更优 (Sharpe: {new_metrics.sharpe_ratio:.2f} > {old_metrics.sharpe_ratio:.2f})"
            )
            return new_model

        logger.info("[Phase 4] 旧模型更优，保留")
        return current_model

    def run_once(self) -> dict:
        """执行单次迭代（训练 → 回测 → 决策 → 可选重训练），返回汇总。"""
        current_model = self.run_initial_training()
        bt = self.run_backtest(current_model)
        metrics = self._to_metrics(Path(current_model).stem, bt)
        decision = self.evaluate_and_decide(metrics)

        if decision == "retrain":
            current_model = self.retrain(current_model)
            bt = self.run_backtest(current_model)

        return {"model_path": current_model, "backtest": bt, "decision": decision}

    def run_loop(self):
        """无限自动迭代循环。"""
        logger.info(f"RL 自动迭代生命周期启动: {self.config.symbol} {self.config.interval}")
        while True:
            self.run_once()
            logger.info(f"等待 {self.config.check_interval_hours}h 后下次检查...")
            time.sleep(self.config.check_interval_hours * 3600)


if __name__ == "__main__":
    from typing import Annotated

    import typer

    app = typer.Typer(help="RL 自动迭代生命周期", add_completion=False)

    @app.command()
    def run(
        symbol: Annotated[str, typer.Option("--symbol", "-s")] = "BTCUSDT",
        interval: Annotated[str, typer.Option("--interval", "-i")] = "1h",
        algorithm: Annotated[str, typer.Option("--algorithm", "-a")] = "ppo",
        train_steps: Annotated[int, typer.Option("--train-steps")] = 30000,
        retrain_steps: Annotated[int, typer.Option("--retrain-steps")] = 10000,
        check_hours: Annotated[int, typer.Option("--check-hours")] = 24,
    ):
        """运行生命周期；--check-hours 0 表示只跑一次。"""
        config = LifecycleConfig(
            symbol=symbol,
            interval=interval,
            algorithm=algorithm,
            train_timesteps=train_steps,
            retrain_timesteps=retrain_steps,
            check_interval_hours=check_hours,
        )
        lifecycle = RLLifecycle(config)
        if check_hours > 0:
            lifecycle.run_loop()
        else:
            lifecycle.run_once()

    app()
