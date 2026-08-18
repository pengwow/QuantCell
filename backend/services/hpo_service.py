"""HPO Service — axon_quant.hpo / axon_quant.walk_forward 业务封装。

通过 axon_hpo (Python) 和 axon_quant.walk_forward (Rust) 调用 axon_quant 的引擎。

用法:
    >>> svc = HPOServiceWrapper()
    >>> result = svc.optimize(
    ...     objective_fn=lambda params: [backtest_with(params)],
    ...     param_space={
    ...         "fast": {"type": "int_uniform", "low": 5, "high": 50, "step": 1},
    ...         "slow": {"type": "int_uniform", "low": 20, "high": 200},
    ...     },
    ...     n_trials=20,
    ... )
    >>> wf = WalkForwardServiceWrapper()
    >>> folds = wf.split(n_samples=1000, train_size=600, test_size=200, step_size=100)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__, LogType.APPLICATION)

# HPO 使用 axon_hpo Python 包(OptunaHPO),比 Rust HPORunner 更灵活
# WalkForward 使用 axon_quant.walk_forward Rust 引擎
try:
    import axon_quant.walk_forward as _walk_forward
    from axon_hpo.optuna_runner import OptunaHPO
    from axon_hpo.types import SearchSpaceDef

    AXON_AVAILABLE = True
except ImportError as e:
    AXON_AVAILABLE = False
    SearchSpaceDef = None
    OptunaHPO = None
    _walk_forward = None
    logger.warning(f"axon_quant 不可用: {e}")


def _build_hpo_config(
    param_space: dict[str, Any],
    n_trials: int,
    direction: str = "maximize",
    study_name: str = "quantcell_hpo",
) -> dict[str, Any]:
    """构造 axon_quant.hpo.HPORunner 所需的 HPOConfig 字典。

    Args:
        param_space: 搜索空间，每个参数为 SearchSpaceDef 字典
            例: {"fast": {"type": "int_uniform", "low": 5, "high": 50, "step": 1}}
            type 支持: uniform, log_uniform, int_uniform, discrete, choice, categorical
        n_trials: 试验次数
        direction: "maximize" 或 "minimize"
        study_name: Optuna study 名称
    """
    # 转换参数空间：确保 type 字段正确（Rust serde tagged enum）
    converted_space = {}
    for name, defn in param_space.items():
        if isinstance(defn, dict):
            # 确保 type 字段存在（兼容 param_type）
            if "type" not in defn and "param_type" in defn:
                defn = {"type": defn["param_type"], **defn}
            converted_space[name] = defn
        else:
            converted_space[name] = defn

    return {
        "study": {
            "study_name": study_name,
            "direction": direction.lower(),
            "load_if_exists": True,
        },
        "search_space": converted_space,
        "objective": {
            "type": "single",
            "direction": direction.lower(),
        },
        "hpo": {
            "n_trials": n_trials,
            "n_jobs": 1,
        },
    }


class HPOServiceWrapper:
    """超参优化服务包装器

    包装 axon_hpo.OptunaHPO（Python + Optuna），
    objective_fn 签名为 `Callable[[dict[str, Any]], list[float]]`，
    返回每个 trial 的目标值列表（多目标也支持）。
    """

    def __init__(self):
        """初始化超参优化服务"""
        if not AXON_AVAILABLE or OptunaHPO is None or SearchSpaceDef is None:
            msg = "axon_hpo 不可用，请安装 axon-quant: pip install axon-quant"
            raise RuntimeError(msg)
        logger.info("HPOService 已初始化（axon_hpo.OptunaHPO）")

    @staticmethod
    def _param_dict_to_search_space_def(param_dict: dict[str, Any]) -> SearchSpaceDef:
        """将参数字典转为 SearchSpaceDef 对象。

        Args:
            param_dict: {"type": "int_uniform", "low": 5, "high": 50, "step": 1}

        Returns:
            SearchSpaceDef 对象
        """
        if SearchSpaceDef is None:
            msg = "SearchSpaceDef 未加载"
            raise RuntimeError(msg)
        param_type = param_dict.get("type") or param_dict.get("param_type")
        if param_type is None:
            msg = "param_dict 必须包含 type 或 param_type"
            raise ValueError(msg)
        return SearchSpaceDef(
            param_type=param_type,
            low=param_dict.get("low"),
            high=param_dict.get("high"),
            step=param_dict.get("step"),
            choices=param_dict.get("choices"),
            log=param_dict.get("log", False),
        )

    def optimize(
        self,
        objective_fn: Callable[[dict[str, Any]], list[float]],
        param_space: dict[str, Any],
        n_trials: int = 10,
        direction: str = "maximize",
        study_name: str = "quantcell_hpo",
    ) -> dict[str, Any]:
        """执行超参优化

        Args:
            objective_fn: 目标函数，接收参数字典，返回目标值列表
                例: lambda params: [backtest_sharpe(params)]
            param_space: 搜索空间，每个参数为 SearchSpaceDef 字典
                例: {"fast": {"type": "int_uniform", "low": 5, "high": 50, "step": 1}}
            n_trials: 试验次数
            direction: "maximize" 或 "minimize"
            study_name: Optuna study 名称

        Returns:
            HPO 结果字典，包含:
            - best_trial: 最佳 trial（params + values）
            - all_trials: 所有 trial 列表
            - elapsed_ms: 总耗时
        """
        # 将字典转换为 SearchSpaceDef 对象
        search_space = {name: self._param_dict_to_search_space_def(defn) for name, defn in param_space.items()}

        hpo_runner = OptunaHPO(
            search_space=search_space,
            objective_fn=objective_fn,
            study_name=study_name,
            directions=direction,
        )
        trial_results = hpo_runner.run(n_trials=n_trials)

        # 转换为字典格式
        all_trials = []
        best_trial = None
        best_value = None
        direction_is_maximize = direction.lower() == "maximize"

        for tr in trial_results:
            trial_dict = {
                "trial_id": tr.trial_id,
                "params": tr.params,
                "values": tr.values,
                "state": tr.state,
                "duration_ms": tr.duration_ms,
            }
            all_trials.append(trial_dict)
            # 找最佳 trial
            if tr.state == "complete" and tr.values:
                current_value = tr.values[0]
                if (
                    best_trial is None
                    or (direction_is_maximize and current_value > best_value)
                    or (not direction_is_maximize and current_value < best_value)
                ):
                    best_trial = trial_dict
                    best_value = current_value

        elapsed_ms = sum(tr.duration_ms for tr in trial_results)

        result = {
            "best_trial": best_trial,
            "all_trials": all_trials,
            "elapsed_ms": elapsed_ms,
        }
        logger.info(f"HPO 完成: trials={len(all_trials)}, elapsed_ms={elapsed_ms}")
        return result


class WalkForwardServiceWrapper:
    """前向验证服务包装器

    包装 axon_quant.walk_forward.WalkForwardRunner（Rust），
    提供时间序列分割功能。每个 fold 包含 train/validation/test 三段索引区间，
    调用方负责对每个 fold 执行训练 + 验证 + 测试。
    """

    def __init__(self):
        """初始化前向验证服务"""
        if not AXON_AVAILABLE:
            msg = "axon_quant.walk_forward 不可用，请安装 axon_quant: pip install axon-quant"
            raise RuntimeError(msg)
        logger.info("WalkForwardService 已初始化（axon_quant.walk_forward.WalkForwardRunner）")

    def split(
        self,
        n_samples: int,
        train_size: int = 600,
        test_size: int = 200,
        step_size: int = 100,
        validation_size: int = 0,
        mode: str = "rolling",
    ) -> list[dict[str, int]]:
        """分割数据为 walk-forward folds

        Args:
            n_samples: 总样本数
            train_size: 训练窗口大小
            test_size: 测试窗口大小
            step_size: 滑动步长
            validation_size: 验证窗口大小（0 表示无验证集）
            mode: "rolling"（固定窗口滑动）或 "expanding"（训练窗口递增）

        Returns:
            fold 列表，每个 fold 是字典:
            - fold_id: fold 序号
            - train_start, train_end: 训练集索引区间
            - validation_start, validation_end: 验证集索引区间（无验证集时与 train 重合）
            - test_start, test_end: 测试集索引区间
        """
        config = self._build_config(train_size, test_size, step_size, validation_size, mode)
        runner = _walk_forward.WalkForwardRunner(config)
        folds = runner.split(n_samples)
        logger.info(f"Walk-Forward 分割: {len(folds)} folds, mode={mode}")
        return folds

    @staticmethod
    def _build_config(
        train_size: int,
        test_size: int,
        step_size: int,
        validation_size: int,
        mode: str,
    ) -> dict[str, Any]:
        """构造 WalkForwardConfig 字典。

        window_type: "rolling"（固定窗口滑动）或 "expanding"（训练窗口递增）。
        expanding 模式下 step_size 通常等于 test_size。
        """
        window_type = "expanding" if mode == "expanding" else "rolling"
        return {
            "train_size": train_size,
            "validation_size": validation_size,
            "test_size": test_size,
            "step_size": step_size,
            "window_type": window_type,
        }

    def validate(
        self,
        strategy_fn: Callable[[dict[str, int], dict[str, int]], float],
        data: Any,
        n_splits: int = 5,
        mode: str = "rolling",
    ) -> dict[str, Any]:
        """执行前向验证

        Args:
            strategy_fn: 策略函数，接收 (train_indices, test_indices)，返回评估指标
            data: 数据（用于确定总样本数）
            n_splits: 期望的 fold 数（实际由窗口大小决定）
            mode: "rolling" 或 "expanding"

        Returns:
            验证结果字典，包含:
            - folds: fold 列表
            - metrics: 每个 fold 的评估指标
            - aggregate: 聚合指标（mean, std, deflated_sharpe）
        """
        # 从 data 推断 n_samples
        if hasattr(data, "__len__"):
            n_samples = len(data)
        else:
            msg = "data 必须支持 len()"
            raise ValueError(msg)

        # 自动计算窗口大小，使 fold 数约为 n_splits
        if n_samples <= 0:
            msg = "n_samples 必须大于 0"
            raise ValueError(msg)

        test_size = max(1, n_samples // (n_splits + 2))
        train_size = max(test_size, n_samples - test_size * (n_splits + 1))
        step_size = test_size

        folds = self.split(
            n_samples=n_samples,
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            mode=mode,
        )

        metrics: list[float] = []
        for fold in folds:
            train_idx = {"start": fold["train_start"], "end": fold["train_end"]}
            test_idx = {"start": fold["test_start"], "end": fold["test_end"]}
            try:
                m = float(strategy_fn(train_idx, test_idx))
                metrics.append(m)
            except Exception as e:
                logger.warning(f"Fold {fold.get('fold_id')} 评估失败: {e}")
                metrics.append(0.0)

        # 聚合
        if metrics:
            mean = sum(metrics) / len(metrics)
            variance = sum((x - mean) ** 2 for x in metrics) / len(metrics)
            std = variance**0.5
        else:
            mean = std = 0.0

        return {
            "folds": folds,
            "metrics": metrics,
            "aggregate": {
                "mean": mean,
                "std": std,
                "n_folds": len(folds),
            },
        }


class HPOServiceProxy:
    """超参优化服务代理

    当 axon_quant 不可用时提供空实现，避免业务代码崩溃。
    """

    def __init__(self):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._hpo_service = HPOServiceWrapper()
                self._wf_service = WalkForwardServiceWrapper()
            except Exception as e:
                logger.error(f"创建 HPOService 失败: {e}")
                self._available = False
                self._hpo_service = None
                self._wf_service = None
        else:
            self._hpo_service = None
            self._wf_service = None
            logger.warning("axon_quant.hpo 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.hpo 是否可用"""
        return self._available

    def optimize(
        self,
        objective_fn: Callable[[dict[str, Any]], list[float]],
        param_space: dict[str, Any],
        n_trials: int = 10,
        direction: str = "maximize",
        study_name: str = "quantcell_hpo",
    ) -> dict[str, Any]:
        """执行超参优化"""
        if not self._available or not self._hpo_service:
            return {"status": "not_available"}
        return self._hpo_service.optimize(objective_fn, param_space, n_trials, direction, study_name)

    def split(
        self,
        n_samples: int,
        train_size: int = 600,
        test_size: int = 200,
        step_size: int = 100,
        mode: str = "rolling",
    ) -> list[dict[str, int]]:
        """分割 walk-forward folds"""
        if not self._available or not self._wf_service:
            return []
        return self._wf_service.split(n_samples, train_size, test_size, step_size, mode=mode)

    def validate(
        self,
        strategy_fn: Callable[[dict[str, int], dict[str, int]], float],
        data: Any,
        n_splits: int = 5,
        mode: str = "rolling",
    ) -> dict[str, Any]:
        """执行前向验证"""
        if not self._available or not self._wf_service:
            return {"status": "not_available"}
        return self._wf_service.validate(strategy_fn, data, n_splits, mode)
