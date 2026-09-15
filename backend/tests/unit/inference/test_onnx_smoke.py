"""P2:ONNX 推理 / 热更新冒烟测试。

覆盖评估报告 E 区「ONNX 推理:模型加载/热更新」缺口:
- create_onnx_engine 加载程序化构造的微型 ONNX 模型
- infer 输出合法 Action(3 概率 argmax → buy/sell/hold)
- infer_batch 批量一致性
- 特征维度不匹配 → InferenceError(DimensionMismatch)
- ModelHotReloader 手动 reload → 版本递增 + 回调触发

Rust ort 运行时需要动态库;通过 ORT_DYLIB_PATH 指向 pip onnxruntime
自带的 dylib(在模块导入时、首次引擎构造前设置)。
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

onnx = pytest.importorskip("onnx", reason="onnx 未安装")
pytest.importorskip("onnxruntime", reason="onnxruntime 未安装")


def _ensure_ort_dylib() -> None:
    """为 Rust ort 指定 pip onnxruntime 的动态库(须在任何引擎构造前执行)。"""
    if os.environ.get("ORT_DYLIB_PATH"):
        return
    spec = importlib.util.find_spec("onnxruntime")
    if spec is None or spec.submodule_search_locations is None:
        return
    capi = Path(next(iter(spec.submodule_search_locations))) / "capi"
    for dylib in sorted(capi.glob("libonnxruntime*.dylib"), reverse=True):
        os.environ["ORT_DYLIB_PATH"] = str(dylib)
        return


_ensure_ort_dylib()

from axon_quant.inference import InferenceError, ModelHotReloader, Observation, create_onnx_engine


def _build_identity_model(path: Path) -> None:
    """构造 input[1,1,3] → Identity → output 的微型模型,便于精确控制概率。"""
    from onnx import TensorProto, helper

    node = helper.make_node("Identity", ["input"], ["output"])
    graph = helper.make_graph(
        [node],
        "tiny",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 1, 3])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1, 3])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.save(model, path)


@pytest.fixture(scope="module")
def onnx_model_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("onnx_smoke") / "tiny_model.onnx"
    _build_identity_model(path)
    return path


@pytest.fixture(scope="module")
def engine(onnx_model_path: Path):
    return create_onnx_engine(str(onnx_model_path), (1, 1, 3), 3)


def test_infer_maps_probs_to_action(engine) -> None:
    """单条推理:3 概率 argmax → buy/sell/hold,confidence 取最大概率。"""
    cases = [
        ([0.9, 0.05, 0.05], "buy"),
        ([0.1, 0.8, 0.1], "sell"),
        ([0.1, 0.2, 0.7], "hold"),
    ]
    for features, expected in cases:
        action = engine.infer(Observation(symbol="BTC-USDT", timestamp_ns=1_700_000_000, features=features))
        assert str(action.action_type).split(".")[-1].lower() == expected
        assert action.confidence == pytest.approx(max(features), abs=1e-5)
        # target_position 取 probs[0](identity 模型下即首个特征)
        assert action.target_position == pytest.approx(features[0], abs=1e-5)


def test_infer_batch_consistent_with_single(engine) -> None:
    """批量推理与逐条推理结果一致。"""
    observations = [
        Observation(symbol="BTC-USDT", timestamp_ns=1, features=[0.9, 0.05, 0.05]),
        Observation(symbol="ETH-USDT", timestamp_ns=2, features=[0.1, 0.8, 0.1]),
    ]
    batch_actions = engine.infer_batch(observations)
    single_actions = [engine.infer(obs) for obs in observations]

    assert len(batch_actions) == 2
    for batch_action, single_action in zip(batch_actions, single_actions, strict=True):
        assert batch_action.action_type == single_action.action_type
        assert batch_action.target_position == pytest.approx(single_action.target_position, abs=1e-6)


def test_infer_feature_dim_mismatch_raises(engine) -> None:
    """特征数与 input_shape 不符 → InferenceError(DimensionMismatch)。"""
    with pytest.raises(InferenceError, match="DimensionMismatch"):
        engine.infer(Observation(symbol="X", timestamp_ns=1, features=[0.1, 0.2]))


def test_hot_reloader_version_increments_and_fires_callback(engine) -> None:
    """热更新:reload 版本单调递增,subscribe 的回调收到 (path, version)。"""
    reloader = ModelHotReloader(engine)
    assert reloader.version() == 0
    assert reloader.has_callback() is False

    events: list[tuple[str, int]] = []
    reloader.subscribe(lambda path, version: events.append((path, version)))
    assert reloader.has_callback() is True

    version1 = reloader.reload()
    version2 = reloader.reload()
    assert version1 >= 1
    assert version2 > version1
    assert reloader.version() == version2

    # 两次 reload 都触发回调,携带模型路径与新版本号
    assert len(events) == 2
    assert events[0][1] == version1
    assert events[1][1] == version2
    assert events[0][0] == reloader.model_path
