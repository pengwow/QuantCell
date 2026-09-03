"""Worker 自动迭代生命周期

支持两种策略类型的自动优化：
- 规则策略：自动优化参数（ Optuna HPO）
- RL 策略：自动重训练模型

自动循环：评估 → 优化 → 部署 → 监控 → 触发优化

使用：python -m worker.lifecycle --worker-id 1 --mode auto
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class WorkerLifecycleConfig:
    """Worker 生命周期配置"""

    worker_id: int
    strategy_type: str = "rule"  # rule / rl
    # 优化参数
    check_interval_hours: int = 24
    max_retrain_age_days: int = 7
    min_sharpe: float = 0.5
    max_drawdown_pct: float = 5.0
    # RL 专用
    retrain_timesteps: int = 10000
    # 规则策略专用
    hpo_trials: int = 20
    hpo_timesteps: int = 5000


class WorkerLifecycle:
    """Worker 自动迭代生命周期"""

    def __init__(self, config: WorkerLifecycleConfig):
        self.config = config
        self._running = False

    def run(self):
        """启动自动循环"""
        self._running = True
        logger.info(f"Worker {self.config.worker_id} 生命周期启动 (type={self.config.strategy_type})")

        while self._running:
            try:
                self._iteration()
            except Exception as e:
                logger.error(f"迭代失败: {e}")

            if self._running:
                logger.info(f"等待 {self.config.check_interval_hours}h 后下次检查...")
                time.sleep(self.config.check_interval_hours * 3600)

    def stop(self):
        self._running = False

    def _iteration(self):
        """执行一次迭代"""
        if self.config.strategy_type == "rl":
            self._rl_iteration()
        else:
            self._rule_iteration()

    def _rl_iteration(self):
        """RL 策略迭代：评估 → 重训练 → 比较 → 部署"""
        logger.info("[RL] 开始迭代优化")

        # 评估当前模型
        current_metrics = self._evaluate_current()
        logger.info(f"[RL] 当前表现: PnL=${current_metrics.get('pnl', 0):.2f}")

        # 检查是否需要重训练
        if self._should_retrain(current_metrics):
            logger.info("[RL] 触发重训练")
            new_model = self._retrain()
            new_metrics = self._evaluate_model(new_model)

            if new_metrics.get("sharpe", 0) > current_metrics.get("sharpe", 0):
                logger.info("[RL] 新模型更优，部署中...")
                self._deploy(new_model)
            else:
                logger.info("[RL] 旧模型更优，保留")

    def _rule_iteration(self):
        """规则策略迭代：评估 → HPO → 比较 → 部署"""
        logger.info("[Rule] 开始迭代优化")

        # 评估当前参数
        current_metrics = self._evaluate_current()
        logger.info(f"[Rule] 当前表现: PnL=${current_metrics.get('pnl', 0):.2f}")

        # 检查是否需要优化
        if self._should_optimize(current_metrics):
            logger.info("[Rule] 触发参数优化")
            new_params = self._optimize_params()
            new_metrics = self._evaluate_params(new_params)

            if new_metrics.get("sharpe", 0) > current_metrics.get("sharpe", 0):
                logger.info("[Rule] 新参数更优，部署中...")
                self._deploy_params(new_params)
            else:
                logger.info("[Rule] 当前参数更优，保留")

    def _evaluate_current(self) -> dict:
        """评估当前策略表现。

        ponytail: 当前尚未持久化“已部署模型/参数”的引用，无法量化真实表现，
        因此返回空指标会持续触发重训练/优化。已知上限：无状态评估。
        升级路径：接入 worker 状态后根据最近交易记录计算真实指标替换此处。
        """
        return {"pnl": 0.0, "sharpe": 0.0, "trades": 0, "drawdown": 0.0}

    def _should_retrain(self, metrics: dict) -> bool:
        """RL: 检查是否需要重训练"""
        if metrics.get("trades", 0) < 10:
            return True
        if metrics.get("sharpe", 0) < self.config.min_sharpe:
            return True
        return metrics.get("drawdown", 0) > self.config.max_drawdown_pct

    def _should_optimize(self, metrics: dict) -> bool:
        """规则策略: 检查是否需要优化参数"""
        return self._should_retrain(metrics)

    @staticmethod
    def _load_market_data(symbol: str = "BTCUSDT", interval: str = "15m"):
        """加载本地K线数据（统一走 BacktestDataProvider，替代旧 rl.service 的下发逻辑）。"""
        from backtest.data_provider import BacktestDataProvider

        return BacktestDataProvider().load_klines(symbol, interval)

    def _retrain(self) -> str:
        """RL: 重训练模型（委托统一 RLService 完成训练与保存）。"""
        from services.rl_service import RLService, RLTrainConfig

        config = RLTrainConfig(
            symbol="BTCUSDT",
            interval="15m",
            algorithm="ppo",
            total_timesteps=self.config.retrain_timesteps,
            model_name=f"worker_{self.config.worker_id}",
        )
        result = RLService().train(config)
        logger.info(f"[RL] 重训练完成: {result.model_path}")
        return result.model_path

    def _optimize_params(self) -> dict:
        """规则策略: 优化参数"""
        import optuna

        def objective(trial):
            fast = trial.suggest_int("fast", 5, 20)
            slow = trial.suggest_int("slow", 20, 50)
            if fast >= slow:
                return -1000

            # 用当前数据回测
            from backtest.backtest_loop import BacktestLoop
            from strategy.base import StrategyConfig
            from strategy.templates.sma_crossover import SMACrossover

            df = self._load_market_data()
            config = StrategyConfig(
                name="sma_crossover",
                symbol="BTCUSDT",
                params={"fast": fast, "slow": slow},
            )
            strategy = SMACrossover(config)
            r = BacktestLoop(initial_cash=100_000).run(strategy, df.head(5000), "BTCUSDT")
            return r.total_pnl

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=self.config.hpo_trials, show_progress_bar=False)

        return study.best_params

    def _evaluate_model(self, model_path: str) -> dict:
        """评估 RL 模型（使用统一 RLService 的真实回测指标）。"""
        from services.rl_service import RLService

        bt = RLService().run_backtest(model_path, "BTCUSDT", "15m")
        return {
            "pnl": bt.get("total_pnl", 0.0),
            "sharpe": bt.get("sharpe_ratio", 0.0),
            "trades": bt.get("num_trades", 0),
            "drawdown": abs(bt.get("max_drawdown_pct", 0.0)),
        }

    def _evaluate_params(self, params: dict) -> dict:
        """评估规则策略参数"""
        from backtest.backtest_loop import BacktestLoop
        from strategy.base import StrategyConfig
        from strategy.templates.sma_crossover import SMACrossover

        df = self._load_market_data()
        config = StrategyConfig(
            name="sma_crossover",
            symbol="BTCUSDT",
            params={"fast": params.get("fast", 10), "slow": params.get("slow", 30)},
        )
        strategy = SMACrossover(config)
        r = BacktestLoop(initial_cash=100_000).run(strategy, df.head(5000), "BTCUSDT")

        return {
            "pnl": r.total_pnl,
            "sharpe": r.sharpe_ratio,
            "trades": r.fills,
            "drawdown": r.max_drawdown,
        }

    def _deploy(self, model_path: str):
        """部署 RL 模型"""
        logger.info(f"[RL] 部署模型: {model_path}")

    def _deploy_params(self, params: dict):
        """部署规则策略参数"""
        logger.info(f"[Rule] 部署参数: {params}")


if __name__ == "__main__":
    from typing import Annotated

    import typer

    app = typer.Typer(help="Worker 自动迭代生命周期", add_completion=False)

    @app.command()
    def run(
        worker_id: Annotated[int, typer.Option("--worker-id", help="Worker ID")],
        strategy_type: Annotated[str, typer.Option("--type", help="策略类型 (rule/rl)")] = "rule",
        check_hours: Annotated[int, typer.Option("--check-hours", help="检查间隔（小时）")] = 24,
    ):
        """运行 Worker 生命周期。"""
        config = WorkerLifecycleConfig(
            worker_id=worker_id,
            strategy_type=strategy_type,
            check_interval_hours=check_hours,
        )
        WorkerLifecycle(config).run()

    app()
