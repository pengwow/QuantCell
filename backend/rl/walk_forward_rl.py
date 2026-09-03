"""RL Walk-Forward validation service.

Trains and evaluates RL models across time-series splits for OOS validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from backtest.walk_forward import WalkForwardService
from rl.evaluation import EvaluationMetrics, evaluate_model
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

logger = get_logger(__name__, LogType.APPLICATION)


class RLWalkForwardService:
    """Walk-Forward validation for RL models.

    For each fold: train on train split → evaluate on test split (OOS).
    Aggregates metrics across folds.
    """

    def __init__(self):
        self._wf = WalkForwardService()

    def validate(
        self,
        data: pd.DataFrame,
        env_factory: Callable[[pd.DataFrame], Any],
        algo_cls: Any,
        algo_kwargs: dict[str, Any] | None = None,
        n_splits: int = 5,
        train_ratio: float = 0.7,
        mode: str = "rolling",
        total_timesteps: int = 10_000,
    ) -> dict[str, Any]:
        """Run Walk-Forward validation for an RL model.

        Args:
            data: Full OHLCV DataFrame.
            env_factory: Callable that takes a DataFrame and returns a Gymnasium env.
            algo_cls: SB3 algorithm class (PPO, SAC, DQN).
            algo_kwargs: Extra kwargs for algo_cls constructor.
            n_splits: Number of WF folds.
            train_ratio: Train/test ratio within each fold.
            mode: "rolling" or "expanding".
            total_timesteps: Training timesteps per fold.

        Returns:
            Dict with per-fold OOS metrics and aggregate mean/std.
        """
        if algo_kwargs is None:
            algo_kwargs = {}

        splits_result = self._wf.validate(
            strategy_fn=None,
            data=data,
            n_splits=n_splits,
            train_ratio=train_ratio,
            mode=mode,
        )
        splits = splits_result["splits"]

        folds = []
        for i, split in enumerate(splits):
            train_start = split["train_start"]
            train_end = split["train_end"]
            test_start = split["test_start"]
            test_end = split["test_end"]

            train_data = data.iloc[train_start:train_end].reset_index(drop=True)
            test_data = data.iloc[test_start:test_end].reset_index(drop=True)

            if len(train_data) < 10 or len(test_data) < 10:
                logger.warning(f"[WF] Fold {i}: 数据不足，跳过 (train={len(train_data)}, test={len(test_data)})")
                continue

            logger.info(f"[WF] Fold {i}: train={len(train_data)}, test={len(test_data)}")

            try:
                train_env = env_factory(train_data)
                model = algo_cls("MlpPolicy", train_env, verbose=0, **algo_kwargs)
                model.learn(total_timesteps=total_timesteps)
                train_env.close()

                test_env = env_factory(test_data)
                metrics = evaluate_model(model, test_env)
                test_env.close()

                folds.append(
                    {
                        "fold": i,
                        "train_size": len(train_data),
                        "test_size": len(test_data),
                        "oos_metrics": _metrics_to_dict(metrics),
                    }
                )
            except Exception as e:
                logger.error(f"[WF] Fold {i} 失败: {e}")
                folds.append(
                    {
                        "fold": i,
                        "train_size": len(train_data),
                        "test_size": len(test_data),
                        "error": str(e),
                    }
                )

        aggregate = _aggregate_folds(folds)

        return {
            "n_splits": n_splits,
            "mode": mode,
            "folds": folds,
            "aggregate": aggregate,
        }


def _metrics_to_dict(m: EvaluationMetrics) -> dict[str, Any]:
    return {
        "total_pnl": m.total_pnl,
        "total_return_pct": m.total_return_pct,
        "sharpe_ratio": m.sharpe_ratio,
        "max_drawdown_pct": m.max_drawdown_pct,
        "win_rate": m.win_rate,
        "num_trades": m.num_trades,
        "profit_factor": m.profit_factor,
    }


def _aggregate_folds(folds: list[dict]) -> dict[str, Any]:
    metric_keys = [
        "total_pnl",
        "total_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "win_rate",
        "num_trades",
        "profit_factor",
    ]

    valid_folds = [f for f in folds if "oos_metrics" in f]
    if not valid_folds:
        return {"mean": {}, "std": {}, "n_valid_folds": 0}

    arrays = {k: [] for k in metric_keys}
    for f in valid_folds:
        m = f["oos_metrics"]
        for k in metric_keys:
            arrays[k].append(m.get(k, 0.0))

    mean = {k: round(float(np.mean(v)), 4) for k, v in arrays.items()}
    std = {k: round(float(np.std(v)), 4) for k, v in arrays.items()}

    return {"mean": mean, "std": std, "n_valid_folds": len(valid_folds)}
