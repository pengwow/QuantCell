"""HPO (Hyperparameter Optimization) runner.

Uses axon_quant.hpo when available, otherwise provides a basic implementation.
"""

from __future__ import annotations

from typing import Any, Callable

try:
    from axon_quant.hpo import HPOEngine
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    HPOEngine = None


class HPORunner:
    """Hyperparameter optimization runner.

    Supports basic grid search and random search.
    """

    def __init__(self):
        pass

    def optimize(
        self,
        objective_fn: Callable[[dict], float],
        param_space: dict[str, Any],
        n_trials: int = 10,
    ) -> dict[str, Any]:
        """Execute hyperparameter optimization.

        Args:
            objective_fn: Function that takes params dict and returns score.
            param_space: Parameter space definition.
            n_trials: Number of trials.

        Returns:
            Dict with best_params, best_value, all_trials.
        """
        if AXON_AVAILABLE:
            return self._optimize_with_axon(objective_fn, param_space, n_trials)
        return self._optimize_basic(objective_fn, param_space, n_trials)

    def _optimize_with_axon(
        self,
        objective_fn: Callable[[dict], float],
        param_space: dict[str, Any],
        n_trials: int,
    ) -> dict[str, Any]:
        """Optimize using axon_quant's HPOEngine."""
        engine = HPOEngine()
        result = engine.optimize(
            objective_fn=objective_fn,
            param_space=param_space,
            n_trials=n_trials,
        )
        return {
            "best_params": result.best_params,
            "best_value": result.best_value,
            "n_trials": n_trials,
        }

    def _optimize_basic(
        self,
        objective_fn: Callable[[dict], float],
        param_space: dict[str, Any],
        n_trials: int,
    ) -> dict[str, Any]:
        """Basic random search optimization."""
        import random

        best_params = None
        best_value = float('-inf')
        trials = []

        for _ in range(n_trials):
            params = {}
            for name, spec in param_space.items():
                if spec.get("type") == "int":
                    params[name] = random.randint(spec["low"], spec["high"])
                elif spec.get("type") == "float":
                    params[name] = random.uniform(spec["low"], spec["high"])
                elif spec.get("type") == "choice":
                    params[name] = random.choice(spec["choices"])

            value = objective_fn(params)
            trials.append({"params": params, "value": value})

            if value > best_value:
                best_value = value
                best_params = params

        return {
            "best_params": best_params,
            "best_value": best_value,
            "n_trials": n_trials,
            "trials": trials,
        }
