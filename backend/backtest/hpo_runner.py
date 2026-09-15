"""HPO (Hyperparameter Optimization) runner.

架构:Python orchestrator(OptunaHPO) + Rust evaluator(回测引擎) + Rust 数值工具
(py_validate_search_space / py_compute_pareto_front / py_compute_hypervolume)。

QuantCell 端只做编排与格式转换,搜索、采样、剪枝、多目标 Pareto 前沿
全部委托给引擎 axon_hpo.optuna_runner.OptunaHPO。

0.14.5 Breaking Change:OptunaHPO 的 objective_fn 签名从
(params) -> list[float] 改为 (params, report) -> list[float],report 闭包
由引擎注入,内部调 optuna 原生 trial.report + should_prune,剪枝终于能触发。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from axon_hpo.optuna_runner import OptunaHPO
from axon_hpo.types import (
    PrunerConfig,
    PrunerType,
    SamplerConfig,
    SamplerType,
    SearchSpaceDef,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# 本模块 param_space 格式 → 引擎 SearchSpaceDef 的映射
_SPEC_TO_ENGINE_DEF = {
    "int": lambda s: SearchSpaceDef(param_type="int_uniform", low=s["low"], high=s["high"], step=1),
    "float": lambda s: SearchSpaceDef(param_type="uniform", low=s["low"], high=s["high"]),
    "choice": lambda s: SearchSpaceDef(param_type="choice", choices=s["choices"]),
}


def _to_engine_space(param_space: dict[str, Any]) -> dict[str, SearchSpaceDef]:
    """转换本模块简化格式 → 引擎 SearchSpaceDef,未知类型入口拒绝。"""
    converted: dict[str, SearchSpaceDef] = {}
    for name, spec in param_space.items():
        convert = _SPEC_TO_ENGINE_DEF.get(spec.get("type"))
        if convert is None:
            raise ValueError(f"{name}: 不支持的参数类型 {spec.get('type')!r}(可用: int/float/choice)")
        converted[name] = convert(spec)
    return converted


class HPORunner:
    """Hyperparameter optimization runner, backed by engine `OptunaHPO`。

    0.14.5 起 objective_fn 可选择接收 report 闭包来启用真正的剪枝:
        def my_objective(params, report):
            for step, partial_score in enumerate(...):
                report(step, partial_score)   # 中途差的 trial 被 Optuna 剪掉
            return [final_score]

    不传 report 的旧签名 (params) -> float 也被兼容,但无法剪枝。
    """

    def __init__(self):
        pass

    def optimize(
        self,
        objective_fn: Callable[..., list[float] | float],
        param_space: dict[str, Any],
        n_trials: int = 10,
        *,
        directions: str | list[str] = "maximize",
        sampler_type: str = "tpe",
        pruner_type: str | None = None,
        n_startup_trials: int = 10,
        seed: int | None = None,
        n_jobs: int = 1,
        timeout_seconds: int | None = None,
        study_name: str = "quantcell_hpo",
        storage: str | None = None,
        reference_point: list[float] | None = None,
        **pruner_kwargs: Any,
    ) -> dict[str, Any]:
        """执行超参数优化。

        Args:
            objective_fn: 目标函数。签名可二选一:
                (params) -> float | list[float]          — 不接收 report,无法剪枝
                (params, report) -> float | list[float]  — report(step, value) 触发真正剪枝
            param_space: 搜索空间,格式 {"name": {"type": "int"/"float"/"choice", ...}}。
            n_trials: 总 trial 数。
            directions: 单目标传 "maximize"/"minimize",多目标传 list,默认 "maximize"。
            sampler_type: 采样器类型,默认 tpe。
            pruner_type: 剪枝器类型,None 则不剪枝。0.14.5 起 report 闭包由引擎注入,
                objective_fn 内部调 report(step, value) 后剪枝才真正生效。
            n_startup_trials: TPE 冷启动 trial 数,前 N 个用随机采样。
            seed: 随机种子,None 则每次不同。
            n_jobs: 并行 trial 数,默认 1(单进程)。
            timeout_seconds: 全局超时秒数,None 则不限。
            study_name: Optuna study 名称,持久化时用于复用。
            storage: Optuna 存储 URI,如 "sqlite:///hpo.db",None 则内存临时存储。
            reference_point: 多目标超体积计算的参考点,None 则不计算。
            **pruner_kwargs: 传递给 PrunerConfig 的额外参数(n_warmup_steps / reduction_factor 等)。

        Returns:
            dict: best_params / best_value / n_trials / trials / pareto_front / hypervolume。
                trials 中 state 为 "pruned" 的 trial 表示被剪枝提前终止。

        Raises:
            ValueError: 搜索空间非法(引擎 SearchSpaceDef 校验失败)。
        """
        # 兼容两种签名:自动探测 objective_fn 是否接受 report 参数
        import inspect as _inspect

        try:
            sig = _inspect.signature(objective_fn)
            accepts_report = len(sig.parameters) >= 2
        except TypeError, ValueError:
            accepts_report = False

        _orig = objective_fn

        if accepts_report:
            # 新签名:objective_fn(params, report) -> float/list[float]
            def _wrapped(params: dict, report: Callable[[int, float], None]) -> list[float]:
                result = _orig(params, report)  # type: ignore[arg-type]
                if isinstance(result, (list, tuple)):
                    return list(result)
                return [float(result)]
        else:
            # 旧签名:objective_fn(params) -> float/list[float],忽略 report
            def _wrapped(params: dict, report: Callable[[int, float], None]) -> list[float]:
                result = _orig(params)  # type: ignore[arg-type]
                if isinstance(result, (list, tuple)):
                    return list(result)
                return [float(result)]

        # 采样器配置
        sampler_cfg = SamplerConfig(
            sampler_type=SamplerType(sampler_type),
            seed=seed,
            n_startup_trials=n_startup_trials,
        )

        # 剪枝配置(None 表示不剪枝)
        pruner_cfg: PrunerConfig | None = None
        if pruner_type is not None:
            pruner_cfg = PrunerConfig(
                pruner_type=PrunerType(pruner_type),
                n_startup_trials=pruner_kwargs.pop("n_startup_trials", 5),
                n_warmup_steps=pruner_kwargs.pop("n_warmup_steps", 0),
                reduction_factor=pruner_kwargs.pop("reduction_factor", 3.0),
                min_resource=pruner_kwargs.pop("min_resource", 1),
                max_resource=pruner_kwargs.pop("max_resource", 100),
                **pruner_kwargs,
            )

        hpo = OptunaHPO(
            search_space=_to_engine_space(param_space),
            objective_fn=_wrapped,
            study_name=study_name,
            directions=directions,
            sampler=sampler_cfg,
            pruner=pruner_cfg,
            storage=storage,
        )
        results = hpo.run(n_trials=n_trials, n_jobs=n_jobs, timeout_seconds=timeout_seconds)

        # 结果整理:多目标场景下 get_best_trial() 会抛 RuntimeError,降级为 None
        try:
            best = hpo.get_best_trial()
        except Exception:
            best = None
        trials_out = [
            {
                "trial_id": t.trial_id,
                "params": dict(t.params),
                "values": list(t.values) if t.values else [],
                "state": t.state,
                "duration_ms": t.duration_ms,
                "intermediate_values": t.intermediate_values,
            }
            for t in results
        ]

        pareto: list[dict] = []
        hypervolume: float | None = None
        is_multi = isinstance(directions, list) and len(directions) > 1

        if is_multi:
            pareto = [{"params": dict(p.params), "objectives": list(p.objectives)} for p in hpo.get_pareto_front()]
            if reference_point is not None:
                hypervolume = hpo.compute_hypervolume(reference_point)

        return {
            "best_params": dict(best.params) if best else None,
            "best_value": best.values[0] if best and best.values else float("-inf"),
            "n_trials": n_trials,
            "trials": trials_out,
            "pareto_front": pareto,
            "hypervolume": hypervolume,
        }
