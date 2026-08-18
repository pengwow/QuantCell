"""axon_bridge.inference 适配层 — 模型推理引擎 / ONNX / 烛形。

⚠️ 本模块只做直传重导出,不在 Python 侧实现任何 inference 逻辑。
axon_quant 0.4.0 暴露:
- 类:   InferenceEngine / BatchInferencePipeline / ModelHotReloader
        ModelConfig / BatchConfig / Device / InferenceBackend
        InferenceStats / InferenceError / AxonError
        Action / ActionType / Observation
- 工厂:  create_inference_engine / create_onnx_engine / create_candle_engine
"""

from axon_quant.inference import (
    Action,
    ActionType,
    AxonError,
    BatchConfig,
    BatchInferencePipeline,
    Device,
    InferenceBackend,
    InferenceEngine,
    InferenceError,
    InferenceStats,
    ModelConfig,
    ModelHotReloader,
    Observation,
    create_candle_engine,
    create_inference_engine,
    create_onnx_engine,
)

__all__ = [
    "Action",
    "ActionType",
    "AxonError",
    "BatchConfig",
    "BatchInferencePipeline",
    "Device",
    "InferenceBackend",
    "InferenceEngine",
    "InferenceError",
    "InferenceStats",
    "ModelConfig",
    "ModelHotReloader",
    "Observation",
    "create_candle_engine",
    "create_inference_engine",
    "create_onnx_engine",
]
