"""axon_quant LLM 桥接层 — 全项目统一入口

所有 QuantCell 业务代码通过本模块调用 LLM,不直接 import openai SDK:
- create_llm_backend: 构造 axon_quant LLMBackend
- chat_to_dict / accumulate_stream: 归一化响应(格式对齐旧 OpenAI 语义)
- classify_llm_error: 错误分类(供路由层映射用户文案)

格式差异说明:
- axon 的 finish_reason 是 Rust Debug 格式("Stop"/"ToolCalls"),这里归一化为小写
- axon 的 tool_calls 是 JSON 字符串(function_name 字段),这里解析为
  [{"id", "name", "arguments"(dict)}]
- QuantCell 工具定义是 OpenAI 嵌套格式,axon 要扁平格式,flatten_tools 转换
"""

from __future__ import annotations

import json
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# Rust FinishReason Debug 格式 → OpenAI 风格小写
_FINISH_REASON_MAP = {
    "Stop": "stop",
    "Length": "length",
    "ToolCalls": "tool_calls",
    "ContentFilter": "content_filter",
}


def normalize_finish_reason(raw: str | None) -> str | None:
    """把 axon 的 finish_reason 归一化为小写 OpenAI 风格"""
    if not raw:
        return None
    return _FINISH_REASON_MAP.get(raw, raw.lower())


def parse_tool_calls(raw: str | None) -> list[dict[str, Any]]:
    """解析 axon tool_calls JSON 字符串为 [{id, name, arguments(dict)}]

    axon 格式: [{"id","function_name","arguments"(JSON str)}] 或 "null"
    """
    if not raw or raw == "null":
        return []
    try:
        calls = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"tool_calls JSON 解析失败: {raw[:200]}")
        return []
    result = []
    for tc in calls:
        args = tc.get("arguments", "")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args = {}
        result.append(
            {
                "id": tc.get("id", ""),
                "name": tc.get("function_name", ""),
                "arguments": args,
            }
        )
    return result


def flatten_tools(tools: list[dict] | None) -> list[dict]:
    """OpenAI 嵌套工具定义 → axon 扁平格式

    输入: [{"type":"function","function":{"name","description","parameters"}}]
    输出: [{"name","description","parameters"}]
    已是扁平格式的 dict(无 function 键)原样透传。
    """
    flat = []
    for t in tools or []:
        fn = t.get("function", t)
        flat.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            }
        )
    return flat


def to_axon_messages(messages: list[dict]) -> list[dict]:
    """OpenAI 风格消息列表 → axon dict 消息格式

    - content None → ""(axon 要求 str)
    - assistant 消息的 OpenAI 格式 tool_calls(list) → axon JSON 字符串
    - tool_call_id 透传
    """
    out = []
    for m in messages:
        d: dict[str, Any] = {"role": m.get("role", "user"), "content": m.get("content") or ""}
        if m.get("tool_call_id"):
            d["tool_call_id"] = m["tool_call_id"]
        tcs = m.get("tool_calls")
        if tcs:
            if isinstance(tcs, str):
                d["tool_calls"] = tcs
            else:
                # OpenAI 格式 → axon ToolCall 格式后序列化
                flat = [
                    {
                        "id": tc.get("id", ""),
                        "function_name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", ""),
                    }
                    for tc in tcs
                ]
                d["tool_calls"] = json.dumps(flat, ensure_ascii=False)
        out.append(d)
    return out


def classify_llm_error(e: Exception) -> str:
    """把 axon RuntimeError 消息分类: auth / rate_limit / timeout / network / other"""
    msg = str(e).lower()
    if "auth" in msg or "status 401" in msg or "invalid_api_key" in msg:
        return "auth"
    if "rate limit" in msg or "status 429" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "network" in msg or "connection" in msg:
        return "network"
    return "other"
