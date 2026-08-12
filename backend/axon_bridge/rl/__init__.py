"""axon_bridge.rl 适配层 — 强化学习环境。

⚠️ 本模块只做直传重导出,不在 Python 侧实现任何 RL 逻辑。
axon_quant 0.4.0 暴露: TradingEnv / VERSION
"""
from axon_quant.rl import (  # noqa: F401
    TradingEnv,
    VERSION,
)

__all__ = ["TradingEnv", "VERSION"]
