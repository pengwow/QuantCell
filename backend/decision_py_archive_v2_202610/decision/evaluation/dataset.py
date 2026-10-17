"""离线评测数据集构造。

标签口径在本文件唯一冻结（label_for_return），evaluator/CLI 都只能引用它，
禁止在别处另写一套标签映射。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from decision.questions import build_questions, build_state, request_fingerprint

REQUIRED_COLUMNS: set[str] = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


@dataclass(frozen=True)
class LabeledSample:
    """一个带标签的决策点：end 为窗口最后一根 bar 的下标。"""

    index: int
    fingerprint: str
    state: dict
    questions: dict
    label: str


def load_bars_csv(path: str | Path) -> pd.DataFrame:
    """加载 K 线 CSV 并校验必需列；列缺失直接报错，不做猜测补齐。"""
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV 缺少必需列: {sorted(missing)}")
    return df


def label_for_return(forward_return: float, cost_threshold: float) -> str:
    """冻结标签口径：严格越过双边成本阈值才算信号，等号归 hold。"""
    if forward_return > cost_threshold:
        return "buy"
    if forward_return < -cost_threshold:
        return "sell"
    return "hold"


def build_labeled_samples(
    df: pd.DataFrame,
    *,
    window: int,
    horizon: int,
    cost_threshold: float,
    symbol: str,
    bar_type: str,
) -> list[LabeledSample]:
    """滚动窗口生成样本；最后 horizon 根没有未来收益，不产样本。"""
    n = len(df)
    questions = build_questions(cost_threshold=cost_threshold)
    samples: list[LabeledSample] = []
    # end ∈ [window-1, n-1-horizon]，左右闭区间
    for end in range(window - 1, n - horizon):
        window_df = df.iloc[end - window + 1 : end + 1]
        state = build_state(window_df, symbol=symbol, bar_type=bar_type)
        forward_return = float(df["close"].iloc[end + horizon]) / float(df["close"].iloc[end]) - 1.0
        samples.append(
            LabeledSample(
                index=end,
                fingerprint=request_fingerprint(state, questions),
                state=state,
                questions=questions,
                label=label_for_return(forward_return, cost_threshold),
            )
        )
    return samples
