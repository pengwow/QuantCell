"""AI 文本润色服务 — 通用短文本生成（label/description/name/summary）。

设计目标：
- 复用 axon_bridge.llm 统一入口（create_llm_backend / chat_to_dict），不直连 openai SDK
- prompt 模板按 target 分发，context 提供生成上下文
- 结果截断到 max_length，去除 markdown 代码块/引号等冗余包裹
- 错误分类复用 classify_llm_error，抛出带用户可读文案的异常
- 纯函数设计，可被任意业务模块 import 复用（不仅限因子表单）
"""

from __future__ import annotations

from typing import Any

from axon_bridge.llm import chat_to_dict, classify_llm_error, create_llm_backend
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 各 target 的默认长度上限（字符数），max_length 超过时截断，低于时以 max_length 为准
_DEFAULT_MAX_LENGTH: dict[str, int] = {
    "label": 12,
    "description": 200,
    "name": 40,
    "summary": 500,
}


def _build_messages(target: str, context: dict[str, Any], max_length: int) -> list[dict]:
    """根据 target 构造 system + user 消息。

    每个 target 有独立的 system prompt（角色 + 输出契约），
    user prompt 把 context 里的关键字段渲染进去。
    """
    factor_name = context.get("factor_name", "")
    expression = context.get("expression", "")
    code = context.get("code", "")
    category = context.get("category", "")
    # 描述的已有内容（用于改写场景）
    existing = context.get("existing", "")

    if target == "label":
        system = (
            "你是量化交易因子命名专家。根据因子的英文标识和计算逻辑，"
            "生成一个简洁、专业的中文展示名。\n"
            f"要求：不超过 {max_length} 个汉字，不要加引号，不要解释，只输出名称本身。\n"
            "风格参考：5日动量、成交量异动、波动率反转、均线偏离度。"
        )
        logic = expression or code or ""
        user = f"因子英文标识：{factor_name}\n计算逻辑：{logic}\n分类：{category}\n中文展示名："
    elif target == "description":
        system = (
            "你是量化交易研究员。用一句话描述这个因子的经济含义和计算方式。\n"
            f"要求：不超过 {max_length} 个字符，不要加引号，不要解释，只输出描述本身。\n"
            "风格参考：衡量过去 N 日收益率的动量效应，值越大表示短期上涨趋势越强。"
        )
        logic = expression or code or ""
        existing_hint = f"\n已有描述（可参考或改写）：{existing}" if existing else ""
        user = f"因子英文标识：{factor_name}\n计算逻辑：{logic}\n分类：{category}{existing_hint}\n描述："
    elif target == "name":
        system = (
            "你是量化交易因子命名专家。根据因子的计算逻辑，生成一个简洁的英文标识。\n"
            f"要求：不超过 {max_length} 个字符，仅含小写字母、数字、下划线，以字母开头，"
            "不要加引号，不要解释，只输出标识本身。\n"
            "风格参考：momentum_5d、volume_surge、vol_reversal、ma_deviation。"
        )
        logic = expression or code or ""
        user = f"计算逻辑：{logic}\n分类：{category}\n英文标识："
    else:  # summary
        system = (
            f"你是量化交易研究员。用不超过 {max_length} 个字符总结给定内容的核心要点。"
            "只输出总结本身，不要加引号或解释。"
        )
        user = f"内容：{context.get('text', '')}\n总结："

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _clean_output(text: str, max_length: int) -> str:
    """清理 LLM 输出：去 markdown 包裹、去首尾空白、截断到 max_length。"""
    if not text:
        return ""
    # 去掉首尾空白
    text = text.strip()
    # 去掉 markdown 代码块标记
    if text.startswith("```"):
        # 去掉第一行 ```xxx
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
    text = text.removesuffix("```").strip()
    # 去掉首尾引号（中英文，左右引号可不成对）
    _OPEN_QUOTES = {'"', "'", "“", "‘"}
    _CLOSE_QUOTES = {'"', "'", "”", "’"}
    if len(text) >= 2 and text[0] in _OPEN_QUOTES and text[-1] in _CLOSE_QUOTES:
        text = text[1:-1].strip()
    # 截断
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def _resolve_llm_config(model_id: str | None = None) -> dict[str, Any] | None:
    """解析默认 AI 提供商配置（复用 ai_model.config_utils）。"""
    try:
        from ai_model.config_utils import get_default_provider_and_models

        result = get_default_provider_and_models()
    except Exception as e:
        logger.warning(f"读取 AI 模型配置失败: {e}")
        return None
    if not result:
        return None
    provider = result["provider"]
    api_key = provider.get("api_key")
    if not api_key:
        return None
    enabled = result.get("enabled_models") or []
    model_name = ""
    if model_id:
        model_name = next((m.get("name") for m in enabled if m.get("id") == model_id), model_id)
    elif enabled:
        model_name = enabled[0].get("name", "")
    return {"api_key": api_key, "base_url": provider.get("api_host"), "model": model_name}


class AIPolishError(Exception):
    """AI 润色失败，携带用户可读错误信息。"""

    def __init__(self, message: str, error_type: str = "other"):
        super().__init__(message)
        self.error_type = error_type


async def polish_text(
    target: str,
    context: dict[str, Any],
    max_length: int | None = None,
    model_id: str | None = None,
) -> str:
    """通用 AI 文本润色入口。

    Args:
        target: 生成目标（label/description/name/summary）
        context: 上下文 dict（factor_name/expression/code/category/existing 等）
        max_length: 返回文本最大字符数；None 时取 target 默认值
        model_id: 指定模型 ID；None 时用系统默认模型

    Returns:
        生成并清理后的文本

    Raises:
        AIPolishError: 未配置模型 / LLM 调用失败，消息为用户可读文案
    """
    if max_length is None:
        max_length = _DEFAULT_MAX_LENGTH.get(target, 200)
    max_length = max(1, min(max_length, 2000))

    llm_cfg = _resolve_llm_config(model_id)
    if not llm_cfg:
        raise AIPolishError("请先在「AI 模型设置」中配置并启用一个模型", "no_config")

    messages = _build_messages(target, context, max_length)
    backend = create_llm_backend(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        temperature=0.7,
        max_tokens=min(max_length * 4 + 64, 1024),  # 短文本生成，token 预算收紧
        timeout_secs=30,
    )
    try:
        result = await chat_to_dict(backend, messages)
    except Exception as e:
        kind = classify_llm_error(e)
        if kind == "auth":
            msg = f"AI 模型认证失败：请检查 API Key 是否正确（{e}）"
        elif kind == "rate_limit":
            msg = f"AI 模型请求频率受限，请稍后重试（{e}）"
        elif kind == "timeout":
            msg = f"AI 模型响应超时，请重试或更换模型（{e}）"
        elif kind == "network":
            msg = f"无法连接 AI 模型服务，请检查网络和 API 地址（{e}）"
        else:
            msg = f"AI 模型调用失败：{e}"
        raise AIPolishError(msg, kind) from e

    content = result.get("content") or ""
    cleaned = _clean_output(content, max_length)
    if not cleaned:
        raise AIPolishError("AI 模型返回了空内容，请更换模型或重试", "empty")
    return cleaned
