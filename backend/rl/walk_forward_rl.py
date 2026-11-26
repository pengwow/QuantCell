"""RL Walk-Forward validation service.

Trains and evaluates RL models across time-series splits for OOS validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from backtest.walk_forward import WalkForwardService
from rl.evaluation import EvaluationMetrics, evaluate_model
from services.rl_task_runner import NullReporter, ScaledReporter, TrainingCancelled, learn_in_chunks
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

logger = get_logger(__name__, LogType.APPLICATION)

# 训练窗 / 验证窗统计量对齐阈值(宽松;目标是抓窗口重叠、单位错乱这类数据错配,
# 不是统计检验)。调用方可用 validate(stats_thresholds={...}) 单项覆盖。
STATS_ALIGNMENT_DEFAULTS: dict[str, float] = {
    # 两侧 bar 数之比下限:1 根 vs 500 根这类切分错误直接失败
    "min_bar_ratio": 0.05,
    # 收盘收益率波动率之比区间:量级差 10 倍以上视为口径/单位错乱
    "min_vol_ratio": 0.1,
    "max_vol_ratio": 10.0,
    # 均值差容忍度(以两侧波动率的最大值为单位):随机样本的均值差远小于 3σ
    "mean_diff_in_vol": 3.0,
}


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
        reporter: Any = None,
        stats_thresholds: dict[str, float] | None = None,
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
            reporter: 可选任务上报器（进度 / 日志 / 取消），缺省空实现。
                折内进度按 (已完成折 + 折内进度) / n_splits 折算，stage 取
                `wf_fold_i` / `wf_eval`。
            stats_thresholds: 覆盖 `STATS_ALIGNMENT_DEFAULTS` 的对齐阈值。

        Returns:
            Dict with per-fold OOS metrics and aggregate mean/std, plus an
            `oos` summary used by the promotion gate.
        """
        reporter = reporter if reporter is not None else NullReporter()
        if algo_kwargs is None:
            algo_kwargs = {}
        thresholds = {**STATS_ALIGNMENT_DEFAULTS, **(stats_thresholds or {})}

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

            stats_check = _check_stats_alignment(train_data, test_data, thresholds)
            if not stats_check["passed"]:
                message = "训练窗/验证窗统计量对齐失败: " + "; ".join(stats_check["reasons"])
                logger.warning(f"[WF] Fold {i}: {message}")
                folds.append(
                    {
                        "fold": i,
                        "train_size": len(train_data),
                        "test_size": len(test_data),
                        "error": message,
                        "stats_check": stats_check,
                    }
                )
                continue

            try:
                reporter.check_cancel()
                fold_base = i / max(1, len(splits))
                fold_span = 1.0 / max(1, len(splits))
                reporter.state(
                    stage=f"wf_fold_{i}",
                    progress=fold_base,
                    message=f"Walk-Forward 折 {i + 1}/{len(splits)} 训练",
                )
                train_env = env_factory(train_data)
                model = algo_cls("MlpPolicy", train_env, verbose=0, **algo_kwargs)
                # 折内前 85% 给训练，尾巴留给 OOS 评估
                learn_in_chunks(
                    model,
                    total_timesteps,
                    ScaledReporter(reporter, base=fold_base, span=fold_span * 0.85),
                    stage=f"wf_fold_{i}",
                )
                train_env.close()

                reporter.check_cancel()
                reporter.state(
                    stage="wf_eval",
                    progress=fold_base + fold_span * 0.9,
                    message=f"Walk-Forward 折 {i + 1}/{len(splits)} OOS 评估",
                )
                test_env = env_factory(test_data)
                metrics = evaluate_model(model, test_env)
                test_env.close()

                folds.append(
                    {
                        "fold": i,
                        "train_size": len(train_data),
                        "test_size": len(test_data),
                        "oos_metrics": _metrics_to_dict(metrics),
                        "stats_check": stats_check,
                    }
                )
                reporter.log(f"[WF] 折 {i} 完成: sharpe={metrics.sharpe_ratio:.3f}")
            except TrainingCancelled:
                raise  # 取消不是折失败：直接中止整轮 walk-forward
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
            # 本轮 WF 的 OOS 报告:promote 门槛与 lifecycle 审计按它串轮次。
            # 写进 meta 的 walk_forward.oos,不新增独立落盘通道。
            "oos": _oos_report(aggregate),
        }


def _close_return_stats(data: Any) -> dict[str, Any]:
    """收盘收益率的基础统计量;缺 close 列时返回 None 指标(不参与对齐判定)。"""
    stats: dict[str, Any] = {"bars": len(data), "mean_return": None, "return_vol": None}
    try:
        close = np.asarray(data["close"], dtype=float)
    except KeyError, TypeError, ValueError:
        return stats
    close = close[np.isfinite(close)]
    if close.size < 2:
        stats.update(mean_return=0.0, return_vol=0.0)
        return stats
    returns = np.diff(close) / close[:-1]
    returns = returns[np.isfinite(returns)]
    if returns.size == 0:
        stats.update(mean_return=0.0, return_vol=0.0)
        return stats
    stats.update(mean_return=float(np.mean(returns)), return_vol=float(np.std(returns)))
    return stats


def _check_stats_alignment(
    train_data: Any,
    valid_data: Any,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """比对训练窗/验证窗基础统计量,抓窗口重叠、单位错乱等数据错配。

    宽松相对检查,不是统计检验:bar 数比、收益率波动率比、均值差(以波动率为单位)。
    任一侧统计量缺失只跳过对应检查;恒定价(波动率≈0)两侧一致时视为对齐。
    """
    t = {**STATS_ALIGNMENT_DEFAULTS, **(thresholds or {})}
    train = _close_return_stats(train_data)
    valid = _close_return_stats(valid_data)
    reasons: list[str] = []

    max_bars = max(train["bars"], valid["bars"]) or 1
    bar_ratio = min(train["bars"], valid["bars"]) / max_bars
    if bar_ratio < t["min_bar_ratio"]:
        reasons.append(f"bar 数比异常({train['bars']} vs {valid['bars']})")

    vol_ratio = None
    mean_diff = None
    t_vol, v_vol = train["return_vol"], valid["return_vol"]
    if t_vol is not None and v_vol is not None:
        if t_vol <= 1e-12 and v_vol <= 1e-12:
            pass  # 两侧都是恒定价:无波动可比,不算错配
        elif t_vol <= 1e-12 or v_vol <= 1e-12:
            reasons.append(f"一侧收益率为零波动(train_vol={t_vol:.3g}, valid_vol={v_vol:.3g})")
        else:
            vol_ratio = v_vol / t_vol
            if not (t["min_vol_ratio"] <= vol_ratio <= t["max_vol_ratio"]):
                reasons.append(f"收益率波动率比异常({vol_ratio:.3g})")

    t_mean, v_mean = train["mean_return"], valid["mean_return"]
    if t_mean is not None and v_mean is not None:
        mean_diff = abs(v_mean - t_mean)
        scale = max(t_vol or 0.0, v_vol or 0.0)
        if scale > 1e-12 and mean_diff > t["mean_diff_in_vol"] * scale:
            reasons.append(f"收益率均值差异常({mean_diff:.3g} > {t['mean_diff_in_vol']}×vol)")

    return {
        "passed": not reasons,
        "reasons": reasons,
        "train": train,
        "valid": valid,
        "bar_ratio": round(bar_ratio, 4),
        "vol_ratio": None if vol_ratio is None else round(vol_ratio, 4),
        "mean_diff": None if mean_diff is None else float(mean_diff),
        "thresholds": t,
    }


def _oos_report(aggregate: dict[str, Any]) -> dict[str, Any]:
    """折均 OOS 指标 → promote 门槛消费的每轮报告。

    指标来源是 WF 汇总(aggregate.mean),不重新定义口径;没有有效折时
    evaluable=False,门槛侧据此不拦(见 services.oos_gate)。
    """
    from services.oos_gate import round_passes

    mean = aggregate.get("mean") or {}
    n_valid = int(aggregate.get("n_valid_folds") or 0)
    sharpe = mean.get("sharpe_ratio")
    total_return_pct = mean.get("total_return_pct")
    evaluable = bool(n_valid) and sharpe is not None and total_return_pct is not None
    return {
        "evaluable": evaluable,
        "n_valid_folds": n_valid,
        "sharpe_ratio": sharpe,
        "total_return_pct": total_return_pct,
        "total_pnl": mean.get("total_pnl"),
        "passed": round_passes(sharpe, total_return_pct) if evaluable else None,
        "metric_source": "walk_forward.aggregate.mean",
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
