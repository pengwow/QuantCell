"""Explain Service — axon_quant.explain 可解释性服务（占位，待实现）。

注意：ensemble 功能请使用 services.ensemble_service.EnsembleService，
本模块仅保留 ExplainServiceWrapper 作为 SHAP 可解释性功能的预留接口。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from axon_bridge import explain as _explain

    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _explain = None


class ExplainServiceWrapper:
    """可解释性服务包装器（预留，SHAP 功能待实现）。"""

    def __init__(self):
        if not AXON_AVAILABLE:
            msg = "axon_quant.explain 不可用"
            raise RuntimeError(msg)
        logger.info("ExplainService 已初始化")

    def explain_prediction(
        self,
        model: Any,
        observation: Any,
    ) -> dict[str, Any]:
        """解释预测结果（待实现）。"""
        logger.warning("axon_quant.explain 解释功能暂未实现")
        return {"status": "not_implemented"}
