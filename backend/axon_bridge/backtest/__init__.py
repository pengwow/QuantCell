"""axon_quant.backtest 适配层 — 事件驱动回测,QuantCell 唯一回测来源。

⚠️ QuantCell 自身不实现任何回测逻辑(不保留 VectorEngine / NumPy 向量化)。
本模块仅做直传重导出,业务在 services/backtest_service.py 包装。

axon_quant 0.4.0 提供 5 档撮合:
- L1MatchingEngine           价格优先
- L2MatchingEngine           多档订单簿
- ImpactedMatchingEngine     含市场冲击
- MultiAssetMatchingEngine   多资产并行
"""
from axon_quant import (  # noqa: F401
    BacktestEngine,
    BacktestError,
)
from axon_quant.backtest import (  # noqa: F401
    L1MatchingEngine,
    L2MatchingEngine,
    ImpactedMatchingEngine,
    ImpactedMatchingEngineBuilder,
    MultiAssetMatchingEngine,
)
