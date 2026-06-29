# -*- coding: utf-8 -*-
"""HPO Service — axon_quant.hpo 超参优化服务

包装 axon_quant.hpo，提供超参优化和前向验证功能。
当 axon_quant 不可用时提供清晰的错误信息。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant import hpo as _hpo
    from axon_quant import walk_forward as _walk_forward
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _hpo = None
    _walk_forward = None


class HPOServiceWrapper:
    """超参优化服务包装器

    包装 axon_quant.hpo，提供超参优化功能。

    Example:
        >>> svc = HPOServiceWrapper()
        >>> result = svc.optimize(objective_fn, param_space, n_trials=10)
    """

    def __init__(self):
        """初始化超参优化服务"""
        if not AXON_AVAILABLE:
            raise RuntimeError(
                "axon_quant.hpo 不可用，请安装 axon_quant: pip install axon_quant"
            )
        logger.info("HPOService 已初始化")

    def optimize(
        self,
        objective_fn: Any,
        param_space: dict[str, Any],
        n_trials: int = 10,
    ) -> dict[str, Any]:
        """执行超参优化

        Args:
            objective_fn: 目标函数
            param_space: 参数空间
            n_trials: 试验次数

        Returns:
            优化结果字典
        """
        # TODO: 实现 axon_quant.hpo 集成
        logger.warning("axon_quant.hpo 优化功能暂未实现")
        return {"status": "not_implemented"}


class WalkForwardServiceWrapper:
    """前向验证服务包装器

    包装 axon_quant.walk_forward，提供前向验证功能。

    Example:
        >>> svc = WalkForwardServiceWrapper()
        >>> result = svc.validate(strategy_fn, data, n_splits=5)
    """

    def __init__(self):
        """初始化前向验证服务"""
        if not AXON_AVAILABLE:
            raise RuntimeError(
                "axon_quant.walk_forward 不可用，请安装 axon_quant: pip install axon_quant"
            )
        logger.info("WalkForwardService 已初始化")

    def validate(
        self,
        strategy_fn: Any,
        data: Any,
        n_splits: int = 5,
        mode: str = "rolling",
    ) -> dict[str, Any]:
        """执行前向验证

        Args:
            strategy_fn: 策略函数
            data: 数据
            n_splits: 分割数
            mode: 模式 ("rolling" 或 "expanding")

        Returns:
            验证结果字典
        """
        # TODO: 实现 axon_quant.walk_forward 集成
        logger.warning("axon_quant.walk_forward 验证功能暂未实现")
        return {"status": "not_implemented"}


class HPOServiceProxy:
    """超参优化服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._hpo_service = HPOServiceWrapper()
                self._wf_service = WalkForwardServiceWrapper()
            except Exception as e:
                logger.error(f"创建 HPOService 失败: {e}")
                self._available = False
                self._hpo_service = None
                self._wf_service = None
        else:
            self._hpo_service = None
            self._wf_service = None
            logger.warning("axon_quant.hpo 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.hpo 是否可用"""
        return self._available

    def optimize(
        self,
        objective_fn: Any,
        param_space: dict[str, Any],
        n_trials: int = 10,
    ) -> dict[str, Any]:
        """执行超参优化"""
        if not self._available or not self._hpo_service:
            return {"status": "not_available"}
        return self._hpo_service.optimize(objective_fn, param_space, n_trials)

    def validate(
        self,
        strategy_fn: Any,
        data: Any,
        n_splits: int = 5,
        mode: str = "rolling",
    ) -> dict[str, Any]:
        """执行前向验证"""
        if not self._available or not self._wf_service:
            return {"status": "not_available"}
        return self._wf_service.validate(strategy_fn, data, n_splits, mode)
