"""Worker 自动迭代生命周期

支持两种策略类型的自动优化：
- 规则策略：自动优化参数（ HPORunner + BacktestEvaluator + BacktestLoop）
- RL 策略：自动重训练模型

自动循环：评估 → 优化 → 部署 → 监控 → 触发优化

使用：python -m worker.lifecycle --worker-id 1 --mode auto

规则路径：BaseStrategy → BacktestLoop(内存 DataFrame 直接跑),
HPO 与部署前后评估共用同一引擎,MedianPruner 经 equity_curve 上报真实生效。

ponytail:HPO 是有意保留在 Python BacktestLoop 上的轻量路径——它是参数搜索,
不是部署决策内核(部署回测已走 Rust BacktestRunner)。这样每个 trial 免去
DataFrame→Rust bars 的序列化开销;两条引擎的撮合口径 parity 由
tests/unit/backtest/test_rust_runner_parity.py 守护。
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
    # 品种配置(默认 BTCUSDT 15min)
    symbol: str = "BTCUSDT"
    interval: str = "15m"
    candle_type: str = "spot"
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
    # 回测配置
    initial_capital: float = 100_000.0


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
    def _load_market_data(symbol: str = "BTCUSDT", interval: str = "15min"):
        """加载本地K线数据（统一走 BacktestDataProvider，替代旧 rl.service 的下发逻辑）。"""
        from backtest.data_provider import BacktestDataProvider

        return BacktestDataProvider().load_klines(symbol, interval)

    def _run_rule_backtest(self, df, params: dict) -> dict:
        """跑一次 DualMA 规则策略回测,返回指标字典。

        统一走 BaseStrategy → BacktestLoop(内存 DataFrame,不落盘),
        与 HPO/部署评估共用同一回测路径。
        回测栈依赖较重,函数内延迟导入以保持 worker 模块加载轻量(与 RL 分支一致)。

        ponytail:硬编码 DualMA — 未来换其他规则策略需要 strategy_family 参数,
        当前只聚焦 DualMA 一个策略家族,这里保持最小实现。
        """
        from backtest.backtest_loop import BacktestLoop
        from strategy.base import StrategyConfig
        from strategy.templates.dual_ma import DualMA

        fast = int(params.get("fast", 10))
        slow = int(params.get("slow", 30))
        if fast >= slow:
            return {"_valid": False}

        strategy = DualMA(
            StrategyConfig(
                name="dual_ma",
                symbol=self.config.symbol,
                params={"fast": fast, "slow": slow},
            )
        )
        result = BacktestLoop(initial_cash=self.config.initial_capital).run(
            strategy=strategy, data=df, symbol=self.config.symbol
        )
        return {
            "_valid": True,
            "pnl": result.total_pnl,
            "sharpe": result.sharpe_ratio,
            "trades": result.fills,
            "drawdown": abs(result.max_drawdown_pct),  # 百分比,和 config.max_drawdown_pct 对齐
        }

    def _retrain(self) -> str:
        """RL: 重训练模型（委托统一 RLService 完成训练与保存）。"""
        from services.rl_service import RLService, RLTrainConfig

        config = RLTrainConfig(
            symbol=self.config.symbol,
            interval=self.config.interval,
            algorithm="ppo",
            total_timesteps=self.config.retrain_timesteps,
            model_name=f"worker_{self.config.worker_id}",
        )
        result = RLService().train(config)
        logger.info(f"[RL] 重训练完成: {result.model_path}")
        return result.model_path

    def _optimize_params(self) -> dict:
        """规则策略: HPORunner + BacktestEvaluator + BacktestLoop + DualMA。

        HPO 与 _evaluate_params/部署评估共用 BaseStrategy → BacktestLoop 单一路径;
        build_strategy 内拒绝 fast>=slow,非法参数经 evaluate 统一记 -inf
        (与旧版 _validate_params 过滤等价);优化目标 total_pnl 在固定初始资金下
        与旧 metric="return" 的 argmax 等价。

        evaluator/HPORunner 依赖较重,函数内延迟导入(与 RL 分支一致)。
        """
        from backtest.evaluator import BacktestEvaluator
        from backtest.hpo_runner import HPORunner
        from strategy.base import StrategyConfig
        from strategy.templates.dual_ma import DualMA

        df = self._load_market_data(self.config.symbol, self.config.interval)

        def build_strategy(params: dict):
            fast, slow = int(params["fast"]), int(params["slow"])
            if fast >= slow:
                raise ValueError(f"fast({fast}) 必须小于 slow({slow})")
            return DualMA(
                StrategyConfig(
                    name="dual_ma",
                    symbol=self.config.symbol,
                    params={"fast": fast, "slow": slow},
                )
            )

        # evaluator 与 HPORunner 共用同一 param_space(int/low/high 格式由 HPORunner 消费)
        param_space = {
            "fast": {"type": "int", "low": 5, "high": 20},
            "slow": {"type": "int", "low": 20, "high": 50},
        }
        evaluator = BacktestEvaluator(
            data=df,
            symbol=self.config.symbol,
            build_strategy=build_strategy,
            param_space=param_space,
            initial_cash=self.config.initial_capital,
            metric="total_pnl",
        )

        result = HPORunner().optimize(
            objective_fn=evaluator.evaluate,
            param_space=param_space,
            n_trials=self.config.hpo_trials,
            directions="maximize",
            pruner_type="median",
            n_startup_trials=3,
            n_warmup_steps=5,
            study_name=f"lifecycle_rule_{self.config.worker_id}",
        )

        best = result["best_params"] or {"fast": 10, "slow": 30}
        logger.info(f"[Rule] HPO 优化完成: best={best}, value={result['best_value']:.4f}")
        return best

    def _evaluate_model(self, model_path: str) -> dict:
        """评估 RL 模型（使用统一 RLService 的真实回测指标）。"""
        from services.rl_service import RLService

        bt = RLService().run_backtest(model_path, self.config.symbol, self.config.interval)
        return {
            "pnl": bt.get("total_pnl", 0.0),
            "sharpe": bt.get("sharpe_ratio", 0.0),
            "trades": bt.get("num_trades", 0),
            "drawdown": abs(bt.get("max_drawdown_pct", 0.0)),  # 百分比,和 config 对齐
        }

    def _evaluate_params(self, params: dict) -> dict:
        """评估规则策略参数 — 走和 HPO 完全相同的 BacktestLoop 路径。

        优化与部署评估共用同一回测引擎,消除"优化时一个引擎,评估时另一个引擎"。

        返回字段保持和 _evaluate_current/_evaluate_model 同结构,drawdown 是百分比
        (BacktestResult.max_drawdown_pct 的绝对值),和 config.max_drawdown_pct 一致。
        """
        df = self._load_market_data(self.config.symbol, self.config.interval)
        result = self._run_rule_backtest(df, params)

        if not result.get("_valid"):
            return {"pnl": 0.0, "sharpe": 0.0, "trades": 0, "drawdown": 0.0}

        return {
            "pnl": result["pnl"],
            "sharpe": result["sharpe"],
            "trades": result["trades"],
            "drawdown": result["drawdown"],
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
