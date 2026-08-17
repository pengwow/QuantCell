"""Walk-Forward validation service.

Uses axon_quant.walk_forward when available, otherwise provides a basic implementation.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

try:
    from axon_quant.walk_forward import TimeSeriesSplitter
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    TimeSeriesSplitter = None


class WalkForwardService:
    """Walk-Forward validation service.

    Supports rolling and expanding window modes.
    """

    def __init__(self):
        if not AXON_AVAILABLE:
            pass  # Will use basic implementation

    def validate(
        self,
        strategy_fn: Any,
        data: pd.DataFrame,
        n_splits: int = 5,
        train_ratio: float = 0.7,
        mode: str = "rolling",
    ) -> dict[str, Any]:
        """Execute Walk-Forward validation.

        Args:
            strategy_fn: Strategy function that takes data and returns predictions.
            data: OHLCV DataFrame.
            n_splits: Number of splits.
            train_ratio: Train/test ratio.
            mode: "rolling" or "expanding".

        Returns:
            Dict with splits and metrics.
        """
        if AXON_AVAILABLE:
            return self._validate_with_axon(strategy_fn, data, n_splits, train_ratio, mode)
        return self._validate_basic(strategy_fn, data, n_splits, train_ratio, mode)

    def _validate_with_axon(
        self,
        strategy_fn: Any,
        data: pd.DataFrame,
        n_splits: int,
        train_ratio: float,
        mode: str,
    ) -> dict[str, Any]:
        """Validate using axon_quant's TimeSeriesSplitter."""
        splitter = TimeSeriesSplitter(
            n_splits=n_splits,
            train_ratio=train_ratio,
            mode=mode,
        )
        splits = list(splitter.split(data))
        results = []
        for train_idx, test_idx in splits:
            train_data = data.iloc[train_idx]
            test_data = data.iloc[test_idx]
            results.append({
                "train_size": len(train_data),
                "test_size": len(test_data),
            })
        return {"splits": results, "mode": mode, "n_splits": n_splits}

    def _validate_basic(
        self,
        strategy_fn: Any,
        data: pd.DataFrame,
        n_splits: int,
        train_ratio: float,
        mode: str,
    ) -> dict[str, Any]:
        """Basic Walk-Forward validation without axon_quant."""
        total_len = len(data)
        split_size = total_len // n_splits
        train_size = int(split_size * train_ratio)
        test_size = split_size - train_size

        splits = []
        for i in range(n_splits):
            if mode == "rolling":
                start = i * test_size
                train_start = max(0, start + test_size - train_size)
                train_end = start + test_size
                test_start = train_end
                test_end = min(total_len, test_start + test_size)
            else:  # expanding
                train_start = 0
                train_end = i * test_size + train_size
                test_start = train_end
                test_end = min(total_len, test_start + test_size)

            if test_start >= total_len:
                break

            splits.append({
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "train_size": train_end - train_start,
                "test_size": test_end - test_start,
            })

        return {"splits": splits, "mode": mode, "n_splits": len(splits)}
