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

from ai.config.config_utils import get_all_providers
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
    """两类默认配置的规范指纹：内容变更即失配重建"""
    payload = json.dumps(
        [
            one.get("id"),
            one.get("provider"),
            one.get("api_host"),
            one.get("api_key"),
            one.get("model"),
            two.get("id"),
            two.get("provider"),
            two.get("api_host"),
            two.get("api_key"),
            two.get("model"),
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _default_ai_model(category: str) -> dict:
    """从 system_config 的 ai_model.* 配置读取指定类型的默认模型。

    设置页把配置写入 system_config（键 ``ai_model.{id}.{field}``），
    与 ai_models 表是两条独立链路；本期以 system_config 为唯一配置源。
    """
    providers = [p for p in get_all_providers() if (p.get("category") or "system_two") == category]
    label = "System 1（决策模型）" if category == "system_one" else "System 2（生成式大模型）"
    if not providers:
        msg = f"未配置 {label}，请到「设置 → AI 模型」配置并设为默认"
        raise ValueError(msg)

    defaults = [p for p in providers if p.get("is_default")]
    chosen = defaults[0] if defaults else providers[0]

    models = chosen.get("models") or []
    if not models:
        msg = f"{label} 未填写模型列表，请在设置页补充"
        raise ValueError(msg)

    # is_enabled 存的是设置页选中的模型 ID；未选中时取列表首个
    enabled_id = chosen.get("is_enabled")
    selected = None
    for item in models:
        if isinstance(item, dict) and item.get("id") == enabled_id:
            selected = item
            break
    if selected is None and isinstance(models[0], dict):
        selected = models[0]

    model_name = (selected or {}).get("model_name") or (selected or {}).get("id")
    if not model_name:
        msg = f"{label} 未选择可用模型，请在设置页启用一个模型"
        raise ValueError(msg)

    return {
        "id": chosen.get("id"),
        "provider": chosen.get("provider"),
        "api_host": chosen.get("api_host"),
        "api_key": chosen.get("api_key") or "",
        "model": model_name,
    }


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
        "model": one["model"],
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
    # axon-llm 拒绝空 api_key（"api_key is empty or unset placeholder"），
    # 而本地 ollama / llama-server 无需鉴权，故用占位值占位（不会被实际校验）
    api_key = (two.get("api_key") or "").strip() or "local"
    return make_backend(
        {
            "backends": [
                {
                    "base_url": base_url,
                    "api_key": api_key,
                    "model": two["model"],
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

    one = _default_ai_model("system_one")
    two = _default_ai_model("system_two")

    s2_mode = params.get("s2_mode", "live")
    force_rule = bool(params.get("force_rule", False))
    open_threshold = float(params.get("open_threshold", 0.80))
    hold_threshold = float(params.get("hold_threshold", 0.70))
    s1_timeout = int(params.get("s1_timeout_secs", 5))

    replay_root = Path(replay_dir) if replay_dir else default_replay_dir()
    filename = str(params.get("replay_file") or f"{run_mode or 'run'}.jsonl")
    path = replay_root / filename

    # 缓存键必须带 force_rule（超限切规则层要拿到不含 S2 的新实例）与录制路径
    # （不同策略的 replay_file 不同，否则会复用上一层实例把录制写进错误文件）
    key = (
        one.get("id"),
        two.get("id"),
        _config_fingerprint(one, two),
        open_threshold,
        hold_threshold,
        s1_timeout,
        s2_mode,
        force_rule,
        str(path),
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

    table = DecisionReplayTable(path) if (s2_mode == "replay" and path.is_file()) else None
    wrapped = RecordingCascadeLayer(layer, path, s2_mode=s2_mode, replay_table=table)
    _CACHE[key] = wrapped
    logger.info(
        f"[cascade] layer 装配完成: s2_mode={s2_mode}, force_rule={force_rule}, "
        f"s1_model={one['model']}, s2_model={two['model']}"
    )
    return wrapped
