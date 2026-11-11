"""模型集成聚合器(方案 A,spec §4.1/§5)。

纯函数模块:把 N 个已加载的 RL/SB3 成员模型适配为"obs → ratio(0~1) | None(弃权)"
的统一形态,再按固定均值口径聚合。聚合发生在 Python 侧,不经过 Rust 投票组件
(`axon_quant.ensemble.EnsembleManager` 的 Python 可调用概率恒均匀,方案 A 已弃用)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from gymnasium import spaces

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 离散动作索引 → ratio;hold 不聚合(弃权),用 None 占位而非 0,避免拉低均值
_ACTION_RATIO_MAP: dict[int, float | None] = {0: None, 1: 1.0, 2: 0.0}

# 成员 predict_fn 契约:输入为 1D 特征向量(list[float]),返回 ratio 或 None(弃权)
MemberPredictFn = Callable[[list[float]], "float | None"]

# 若 mean(ratio) 超过该阈值 → buy,否则 hold(spec §5;训练管线 Box(0,1) 仅多头)
BUY_RATIO_EPS = 0.01


def member_ratio_predict_fn(model: Any) -> MemberPredictFn:
    """按成员动作空间分派适配器(Box→clip 连续值;Discrete→动作映射)。"""

    if isinstance(model.action_space, spaces.Discrete):
        return _discrete_to_ratio(model)
    return _continuous_to_ratio(model)


def _continuous_to_ratio(model: Any) -> MemberPredictFn:
    """连续成员:与 rl_service.make_predict_fn 对齐,clip 到 [0,1](仅多头语义)。"""

    def predict(obs: list[float]) -> float:
        action, _ = model.predict(np.asarray(obs, dtype=np.float32), deterministic=True)
        return float(np.clip(np.asarray(action).reshape(-1)[0], 0.0, 1.0))

    return predict


def _discrete_to_ratio(model: Any) -> MemberPredictFn:
    """离散成员:buy→1.0,sell→0.0,hold→None(弃权)。"""

    def predict(obs: list[float]) -> float | None:
        action, _ = model.predict(np.asarray(obs, dtype=np.float32), deterministic=True)
        idx = int(np.asarray(action).reshape(-1)[0])
        return _ACTION_RATIO_MAP.get(idx, None)

    return predict


def aggregate_ratios(member_ratios: list[float | None]) -> tuple[float, float]:
    """spec §5 唯一口径:参与成员均值 + 一致性置信度。

    返回 (ratio, confidence);全体弃权返回 (0.0, 0.0)。
    """
    participated = [r for r in member_ratios if r is not None]
    if not participated:
        return 0.0, 0.0
    ratio = float(np.mean(participated))
    confidence = float(np.clip(1.0 - np.std(participated), 0.0, 1.0))
    return ratio, confidence


def make_ensemble_predict_fn(member_fns: list[MemberPredictFn]) -> Callable[[Any], float]:
    """组合 predict_fn:内核喂一份 obs → 每成员各预测 → 聚合。

    单成员推理异常按 spec §6 吞为弃权(记 warning),不中断整条链路。
    返回值只含 ratio(confidence 不进内核,仅供冒烟 API 展示)。
    """

    def predict(obs: Any) -> float:
        member_ratios: list[float | None] = []
        for i, fn in enumerate(member_fns):
            try:
                member_ratios.append(fn(obs))
            except Exception as e:
                logger.warning(f"集成成员 {i} 推理失败,按弃权处理: {e}")
                member_ratios.append(None)
        ratio, _ = aggregate_ratios(member_ratios)
        return ratio

    return predict
