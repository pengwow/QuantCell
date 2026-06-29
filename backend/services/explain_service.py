# -*- coding: utf-8 -*-
"""Explain Service — axon_quant.explain 可解释性服务

包装 axon_quant.explain，提供 SHAP 特征归因和可解释性功能。
当 axon_quant 不可用时提供清晰的错误信息。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant import explain as _explain
    from axon_quant import ensemble as _ensemble
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _explain = None
    _ensemble = None


class ExplainServiceWrapper:
    """可解释性服务包装器

    包装 axon_quant.explain，提供 SHAP 特征归因和可解释性功能。

    Example:
        >>> svc = ExplainServiceWrapper()
        >>> explanation = svc.explain_prediction(model, observation)
    """

    def __init__(self):
        """初始化可解释性服务"""
        if not AXON_AVAILABLE:
            raise RuntimeError(
                "axon_quant.explain 不可用，请安装 axon_quant: pip install axon_quant"
            )
        logger.info("ExplainService 已初始化")

    def explain_prediction(
        self,
        model: Any,
        observation: Any,
    ) -> dict[str, Any]:
        """解释预测结果

        Args:
            model: 模型实例
            observation: 观测数据

        Returns:
            解释结果字典
        """
        # TODO: 实现 axon_quant.explain 集成
        logger.warning("axon_quant.explain 解释功能暂未实现")
        return {"status": "not_implemented"}


class EnsembleServiceWrapper:
    """模型集成服务包装器

    包装 axon_quant.ensemble，提供模型集成功能。

    Example:
        >>> svc = EnsembleServiceWrapper()
        >>> ensemble_model = svc.create_ensemble(models, strategy="voting")
    """

    def __init__(self):
        """初始化模型集成服务"""
        if not AXON_AVAILABLE:
            raise RuntimeError(
                "axon_quant.ensemble 不可用，请安装 axon_quant: pip install axon_quant"
            )
        logger.info("EnsembleService 已初始化")

    def create_ensemble(
        self,
        models: list[Any],
        strategy: str = "voting",
    ) -> Any:
        """创建集成模型

        Args:
            models: 模型列表
            strategy: 集成策略 ("voting", "stacking", "weighted")

        Returns:
            集成模型实例
        """
        # TODO: 实现 axon_quant.ensemble 集成
        logger.warning("axon_quant.ensemble 集成功能暂未实现")
        return None


class ExplainServiceProxy:
    """可解释性服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._explain_service = ExplainServiceWrapper()
                self._ensemble_service = EnsembleServiceWrapper()
            except Exception as e:
                logger.error(f"创建 ExplainService 失败: {e}")
                self._available = False
                self._explain_service = None
                self._ensemble_service = None
        else:
            self._explain_service = None
            self._ensemble_service = None
            logger.warning("axon_quant.explain 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.explain 是否可用"""
        return self._available

    def explain_prediction(
        self,
        model: Any,
        observation: Any,
    ) -> Optional[dict[str, Any]]:
        """解释预测结果"""
        if not self._available or not self._explain_service:
            return None
        return self._explain_service.explain_prediction(model, observation)

    def create_ensemble(
        self,
        models: list[Any],
        strategy: str = "voting",
    ) -> Optional[Any]:
        """创建集成模型"""
        if not self._available or not self._ensemble_service:
            return None
        return self._ensemble_service.create_ensemble(models, strategy)
