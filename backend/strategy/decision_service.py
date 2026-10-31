"""cascade 决策层装配与缓存。

职责仅为：读 DB 两类默认配置 → 构造 S1/S2 → 装配 PyCascadeLayer → 缓存。
无交易业务判断。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from axon_quant.decision import (
    CascadeConfig,
    RuleFallback,
    SdmCascadeDecisionLayer,
    make_decision_backend,
)
from axon_quant.llm import make_backend

from ai.config.models import AIModelBusiness
from strategy.decision_recording import (
    DecisionReplayTable,
    RecordingCascadeLayer,
    default_replay_dir,
)
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

_CACHE: dict[tuple, RecordingCascadeLayer] = {}


def reset_cache() -> None:
    """清空装配缓存（配置变更或测试用）"""
    _CACHE.clear()


def _config_fingerprint(one: dict, two: dict) -> str:
    """两类默认行内容的规范指纹：内容变更即失配重建（id 不变也能感知）"""
    payload = json.dumps(
        [
            one.get("provider"),
            one.get("api_host"),
            one.get("api_key"),
            one.get("models"),
            two.get("provider"),
            two.get("api_host"),
            two.get("api_key"),
            two.get("models"),
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _require_default(category: str) -> dict:
    """取默认配置；缺失时抛带指引的错误（调用方按上下文转 HTTPException）"""
    row = AIModelBusiness.get_default_model(category, include_api_key=True)
    if not row:
        label = "System 1（决策模型）" if category == "system_one" else "System 2（生成式大模型）"
        msg = f"未配置 {label} 默认模型，请到「设置 → AI 模型」配置并设为默认"
        raise ValueError(msg)
    if not row.get("models"):
        msg = f"{category} 默认模型未填写模型列表，请在设置页补充"
        raise ValueError(msg)
    return row


def _s1_backend(one: dict, params: dict):
    """S1 决策后端：逐 bar 快判，超时从严（默认 5s / 1 次重试）"""
    mode = params.get("s1_mode", "http")
    if mode == "stub":  # 仅供单测：不触网
        return make_decision_backend({"mode": "stub"})
    if not one.get("api_host"):
        msg = "System 1（Laya）默认模型缺少 api_host，请在设置页填写自托管服务地址（不含 /v1）"
        raise ValueError(msg)
    config = {
        "mode": "http",
        "base_url": one["api_host"].rstrip("/"),
        "api_key": one.get("api_key") or "",
        "model": one["models"][0],
        "timeout_secs": int(params.get("s1_timeout_secs", 5)),
        "max_retries": 1,
    }
    return make_decision_backend(config)


def _s2_backend(two: dict):
    """S2 兜底后端：仅 OpenAI 兼容（anthropic 原生协议不经网关不可用）"""
    if not two.get("api_host"):
        msg = "System 2（生成式模型）默认模型缺少 api_host，请在设置页填写服务地址"
        raise ValueError(msg)
    base_url = (two.get("api_host") or "").rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return make_backend(
        {
            "backends": [
                {
                    "base_url": base_url,
                    "api_key": two.get("api_key") or "",
                    "model": two["models"][0],
                }
            ]
        }
    )


def build_cascade_layer(
    params: dict,
    run_mode: str | None = None,
    replay_dir: str | Path | None = None,
) -> RecordingCascadeLayer | None:
    """装配 recording 包装的 cascade layer。

    Args:
        params: 策略参数（读 open_threshold / hold_threshold / s1_timeout_secs /
                s2_mode / s2_max_calls / force_rule / decision_replay / s1_mode）
        run_mode: backtest / paper / live（保留位，当前装配不区分，录制三模式统一）
        replay_dir: 录制目录覆盖（默认 backend/data/decision_replay）

    Returns:
        包装后的 layer；`decision_replay` 模式下返回 None（由策略层查表）
    """
    if params.get("decision_replay"):
        return None

    one = _require_default("system_one")
    two = _require_default("system_two")

    s2_mode = params.get("s2_mode", "live")
    force_rule = bool(params.get("force_rule", False))
    open_threshold = float(params.get("open_threshold", 0.80))
    hold_threshold = float(params.get("hold_threshold", 0.70))
    s1_timeout = int(params.get("s1_timeout_secs", 5))

    # 缓存键必须带 force_rule：超限切规则层后要拿到不含 S2 的新实例，
    # 否则会命中旧缓存把 LLM 版 layer 还回去。
    key = (
        one.get("id"),
        two.get("id"),
        _config_fingerprint(one, two),
        open_threshold,
        hold_threshold,
        s1_timeout,
        s2_mode,
        force_rule,
    )
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    s1 = _s1_backend(one, params)
    cfg = CascadeConfig(open_threshold, hold_threshold)
    if s2_mode == "replay" or force_rule:
        layer = SdmCascadeDecisionLayer(s1, RuleFallback(), cfg)
    else:
        layer = SdmCascadeDecisionLayer.with_llm_fallback(s1, _s2_backend(two), cfg)

    replay_root = Path(replay_dir) if replay_dir else default_replay_dir()
    filename = str(params.get("replay_file") or f"{run_mode or 'run'}.jsonl")
    path = replay_root / filename
    table = DecisionReplayTable(path) if (s2_mode == "replay" and path.is_file()) else None
    wrapped = RecordingCascadeLayer(layer, path, s2_mode=s2_mode, replay_table=table)
    _CACHE[key] = wrapped
    logger.info(
        f"[cascade] layer 装配完成: s2_mode={s2_mode}, force_rule={force_rule}, "
        f"s1_model={one['models'][0]}, s2_model={two['models'][0]}"
    )
    return wrapped
