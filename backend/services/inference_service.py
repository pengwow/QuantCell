# -*- coding: utf-8 -*-
"""Inference Service — axon_quant.inference 推理服务

包装 axon_quant.inference.InferenceEngine，提供模型加载、推理等功能。
当 axon_quant 不可用时提供清晰的错误信息。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)
# axon_quant 导入(走适配层,业务代码不直接 import 第三方包)
try:
    from axon_bridge.inference import (
        InferenceEngine as _InferenceEngine,
        BatchInferencePipeline as _BatchInferencePipeline,
        ModelConfig as _ModelConfig,
        BatchConfig as _BatchConfig,
        create_inference_engine as _create_inference_engine,
        create_onnx_engine as _create_onnx_engine,
        create_candle_engine as _create_candle_engine,
    )
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _InferenceEngine = None
    _BatchInferencePipeline = None
    _ModelConfig = None
    _BatchConfig = None
    _create_inference_engine = None
    _create_onnx_engine = None
    _create_candle_engine = None


class InferenceServiceWrapper:
    """推理服务包装器

    包装 axon_quant.inference.InferenceEngine，提供模型加载、推理等功能。

    Example:
        >>> svc = InferenceServiceWrapper()
        >>> engine = svc.create_engine({"backend": "onnx", "input_shape": [1, 10]})
        >>> engine.load("model.onnx")
        >>> action = engine.infer(observation)
    """

    def __init__(self):
        """初始化推理服务"""
        if not AXON_AVAILABLE:
            raise RuntimeError(
                "axon_quant.inference 不可用，请安装 axon_quant: pip install axon_quant"
            )
        logger.info("InferenceService 已初始化")

    def create_engine(
        self,
        config: dict[str, Any],
        path: Optional[str] = None,
    ) -> Any:
        """创建推理引擎

        Args:
            config: 配置字典，包含:
                - backend: "onnx" 或 "candle"
                - input_shape: 输入形状
                - output_dim: 输出维度
                - device: "cpu" 或 "cuda"
                - fp16: 是否使用半精度
                - num_threads: 线程数
            path: 模型路径（可选）

        Returns:
            InferenceEngine 实例
        """
        model_config = _ModelConfig(**config)
        return _create_inference_engine(model_config, path)

    def create_onnx_engine(
        self,
        config: dict[str, Any],
        path: Optional[str] = None,
    ) -> Any:
        """创建 ONNX 推理引擎

        Args:
            config: 配置字典
            path: 模型路径（可选）

        Returns:
            InferenceEngine 实例
        """
        model_config = _ModelConfig(**config)
        return _create_onnx_engine(model_config, path)

    def create_candle_engine(
        self,
        config: dict[str, Any],
        path: Optional[str] = None,
    ) -> Any:
        """创建 Candle 推理引擎

        Args:
            config: 配置字典
            path: 模型路径（可选）

        Returns:
            InferenceEngine 实例
        """
        model_config = _ModelConfig(**config)
        return _create_candle_engine(model_config, path)

    def create_batch_pipeline(
        self,
        config: dict[str, Any],
    ) -> Any:
        """创建批量推理管道

        Args:
            config: 配置字典

        Returns:
            BatchInferencePipeline 实例
        """
        batch_config = _BatchConfig(**config)
        return _BatchInferencePipeline(batch_config)


class InferenceServiceProxy:
    """推理服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._service = InferenceServiceWrapper()
            except Exception as e:
                logger.error(f"创建 InferenceServiceWrapper 失败: {e}")
                self._available = False
                self._service = None
        else:
            self._service = None
            logger.warning("axon_quant.inference 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.inference 是否可用"""
        return self._available

    def create_engine(
        self,
        config: dict[str, Any],
        path: Optional[str] = None,
    ) -> Optional[Any]:
        """创建推理引擎"""
        if not self._available or not self._service:
            return None
        return self._service.create_engine(config, path)

    def create_onnx_engine(
        self,
        config: dict[str, Any],
        path: Optional[str] = None,
    ) -> Optional[Any]:
        """创建 ONNX 推理引擎"""
        if not self._available or not self._service:
            return None
        return self._service.create_onnx_engine(config, path)

    def create_candle_engine(
        self,
        config: dict[str, Any],
        path: Optional[str] = None,
    ) -> Optional[Any]:
        """创建 Candle 推理引擎"""
        if not self._available or not self._service:
            return None
        return self._service.create_candle_engine(config, path)

    def create_batch_pipeline(
        self,
        config: dict[str, Any],
    ) -> Optional[Any]:
        """创建批量推理管道"""
        if not self._available or not self._service:
            return None
        return self._service.create_batch_pipeline(config)
