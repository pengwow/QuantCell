"""axon_bridge.ensemble 适配层 — 多模型集成 / 投票策略。

⚠️ 本模块只做直传重导出,不在 Python 侧实现任何 ensemble 逻辑。
axon_quant 0.4.0 暴露:
- 类:   EnsembleManager / MetaModel / StackingEnsemble
        HardVoteStrategy / SoftVoteStrategy / WeightedVoteStrategy
        ModelType / ModelWeight / ActionProbabilities
        EnsembleStrategy / EnsembleError
- 类型:  Action / ActionType / Observation (顶层 + ensemble 都暴露,这里走重导出)
"""
from axon_quant.ensemble import (  # noqa: F401
    Action,
    ActionProbabilities,
    ActionType,
    EnsembleError,
    EnsembleManager,
    EnsembleStrategy,
    HardVoteStrategy,
    MetaModel,
    ModelType,
    ModelWeight,
    Observation,
    SoftVoteStrategy,
    StackingEnsemble,
    WeightedVoteStrategy,
)

__all__ = [
    "Action",
    "ActionProbabilities",
    "ActionType",
    "EnsembleError",
    "EnsembleManager",
    "EnsembleStrategy",
    "HardVoteStrategy",
    "MetaModel",
    "ModelType",
    "ModelWeight",
    "Observation",
    "SoftVoteStrategy",
    "StackingEnsemble",
    "WeightedVoteStrategy",
]
