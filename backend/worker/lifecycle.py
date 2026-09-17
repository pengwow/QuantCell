"""Worker 自动迭代生命周期

支持两种策略类型的自动优化：
- 规则策略：自动优化参数（ HPORunner + BacktestEvaluator + EventDrivenBacktestEngine）
- RL 策略：自动重训练模型

自动循环：评估 → 优化 → 部署 → 监控 → 触发优化

使用：python -m worker.lifecycle --worker-id 1 --mode auto

规则策略升级说明：
旧版手写 optuna.create_study + BacktestLoop(纯 Python 撮合) →
新版 HPORunner(OptunaHPO Rust) + BacktestEvaluator + EventDrivenBacktestEngine(Rust)。
统一引擎,部署前后评估一致,MedianPruner 真实生效。
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass

import pandas as pd

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
    # 回测引擎配置(DualMA 专用,多品种/多策略场景可扩展)
    initial_capital: float = 100_000.0
    engine_half_spread: float = 0.001
    engine_depth_levels: int = 4
    engine_size_per_level: float = 50.0
    engine_auto_rebalance_threshold: float = 0.001


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

    # ── 规则策略共享工具（DataFrame → CSV + 引擎/品种配置） ──────────

    def _df_to_csv(self, df, csv_path: str) -> None:
        """把 BacktestDataProvider 返回的 DataFrame 转成 event_engine 能读的 CSV。

        event_engine 默认 timestamp_format="%Y-%m-%d %H:%M:%S"、sep=";",
        这里强制标准 format + sep="," 对齐。
        """
        ts_col = None
        for cand in ("timestamp", "open_time", "datetime"):
            if cand in df.columns:
                ts_col = cand
                break
        if ts_col is None and isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df["timestamp"] = df.index.strftime("%Y-%m-%d %H:%M:%S")
        elif ts_col is not None:
            df = df.copy()
            df["timestamp"] = pd.to_datetime(df[ts_col]).dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            raise ValueError("K线数据缺少 timestamp 列或 DatetimeIndex")

        df.to_csv(csv_path, index=False)

    def _rule_engine_config(self, start_date: str, end_date: str) -> dict:
        """构造规则策略共用的 EventDrivenBacktestEngine 配置。"""
        return {
            "initial_capital": self.config.initial_capital,
            "start_date": start_date,
            "end_date": end_date,
            "half_spread": self.config.engine_half_spread,
            "depth_levels": self.config.engine_depth_levels,
            "size_per_level": self.config.engine_size_per_level,
            "auto_rebalance_threshold": self.config.engine_auto_rebalance_threshold,
        }

    def _run_rule_backtest(self, csv_path: str, params: dict) -> dict:
        """跑一次 DualMA 规则策略回测,返回 RunResult 字典。

        ponytail:硬编码 DualMA — 未来换其他规则策略需要 strategy_family 参数,
        当前只聚焦 DualMA 一个策略家族,这里保持最小实现。
        """
        from decimal import Decimal

        from axon_bridge import swap_instrument
        from backtest.engines.event_engine import EventDrivenBacktestEngine
        from strategies.dual_ma import DualMA, DualMAConfig

        symbol = self.config.symbol
        base, quote = symbol[:-4], symbol[-4:]  # BTCUSDT → BTC, USDT
        ins = swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)
        instrument_id = symbol

        fast = int(params.get("fast", 10))
        slow = int(params.get("slow", 30))
        if fast >= slow:
            return {"_valid": False}

        from datetime import datetime, timedelta

        start = datetime(2025, 1, 1)
        end = start + timedelta(days=30)  # 覆盖大多数场景的默认窗口
        engine = EventDrivenBacktestEngine(
            config=self._rule_engine_config(
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
            )
        )
        engine.initialize()
        engine.add_venue("default", starting_capital=self.config.initial_capital)
        engine.add_instrument(ins)
        engine.load_data_from_csv(csv_path, ins, sep=",")

        strategy = DualMA(
            DualMAConfig(
                instrument_ids=[instrument_id],
                bar_types=[self.config.interval],
                fast_period=fast,
                slow_period=slow,
                trade_size=Decimal("1.0"),
            )
        )
        engine.add_strategy(strategy)
        engine.run_backtest()
        return {"_valid": True, "_rr": engine._engine.run()}

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
        """规则策略: HPORunner + BacktestEvaluator + EventDrivenBacktestEngine + DualMA。

        旧版手写 optuna.create_study + BacktestLoop(纯 Python 撮合),
        新版统一用 Rust EventDrivenBacktestEngine,部署前后评估一致,MedianPruner 真实生效。
        """
        from datetime import datetime, timedelta

        from axon_bridge import swap_instrument
        from backtest.evaluator import BacktestEvaluator
        from backtest.hpo_runner import HPORunner

        # 加载数据 → 临时 CSV(evaluator 接受 csv_path,避免 DataFrame 跨 trial 序列化/复制)
        df = self._load_market_data(self.config.symbol, self.config.interval)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            self._df_to_csv(df, tmp_path)

            base, quote = self.config.symbol[:-4], self.config.symbol[-4:]
            ins = swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)

            start = datetime(2025, 1, 1)
            end = start + timedelta(days=30)
            evaluator = BacktestEvaluator(
                csv_path=tmp_path,
                instrument_dict=ins,
                instrument_id=self.config.symbol,
                engine_config=self._rule_engine_config(
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                ),
                initial_cash=self.config.initial_capital,
            )

            def build_strategy(params: dict):
                import sys
                from decimal import Decimal

                sys.path.insert(0, "strategies")
                from strategies.dual_ma import DualMA, DualMAConfig

                return DualMA(
                    DualMAConfig(
                        instrument_ids=[self.config.symbol],
                        bar_types=[self.config.interval],
                        fast_period=int(params["fast"]),
                        slow_period=int(params["slow"]),
                        trade_size=Decimal("1.0"),
                    )
                )

            # DualMA 特有的非法参数校验:fast < slow
            class _DualMAEvaluator(BacktestEvaluator):
                def _validate_params(_self, params: dict) -> bool:
                    return int(params.get("fast", 0)) < int(params.get("slow", 0))

            evaluator.__class__ = _DualMAEvaluator

            objective = evaluator.make_objective(build_strategy, metric="return")

            result = HPORunner().optimize(
                objective_fn=objective,
                param_space={
                    "fast": {"type": "int", "low": 5, "high": 20},
                    "slow": {"type": "int", "low": 20, "high": 50},
                },
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

        finally:
            os.unlink(tmp_path)

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
        """评估规则策略参数 — 走和 HPO 完全相同的 EventDrivenBacktestEngine。

        旧版 BacktestLoop 撮合结果和 EventDrivenBacktestEngine 不同,导致
        '优化时一个引擎,评估时另一个引擎'的不一致,新版统一为 Rust 引擎。

        返回字段保持和 _evaluate_current/_evaluate_model 同结构,drawdown 是百分比
        (RunResult.max_drawdown_pct 的绝对值),和 config.max_drawdown_pct 一致。
        """
        import tempfile

        df = self._load_market_data(self.config.symbol, self.config.interval)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            self._df_to_csv(df, tmp_path)
            result = self._run_rule_backtest(tmp_path, params)
        finally:
            os.unlink(tmp_path)

        if not result.get("_valid"):
            return {"pnl": 0.0, "sharpe": 0.0, "trades": 0, "drawdown": 0.0}

        rr = result["_rr"]
        return {
            "pnl": rr.total_pnl,
            "sharpe": rr.sharpe_ratio,
            "trades": rr.fills,
            "drawdown": abs(rr.max_drawdown_pct),  # 百分比绝对值,和 config.max_drawdown_pct 对齐
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
